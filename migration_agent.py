import json
import os
from urllib.parse import urlparse, urlunparse
from sqlalchemy import create_engine, text
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from database import get_mongo_client
from dotenv import load_dotenv

load_dotenv()


def ensure_database_exists():
    """Extracts base connection string without DB name and ensures target DB exists."""
    full_uri = os.getenv("MYSQL_URI")
    if not full_uri:
        raise ValueError("MYSQL_URI is not set in the environment variables.")

    # Parse URI to derive base URI (strip out database path like '/target_migration_db')
    parsed = urlparse(full_uri)
    db_name = parsed.path.lstrip("/")  # Extract 'target_migration_db'

    # Reconstruct URI without target database in path
    base_parsed = parsed._replace(path="")
    base_uri = urlunparse(base_parsed)

    # Connect to MySQL instance and create database if missing
    temp_engine = create_engine(base_uri)
    with temp_engine.connect() as conn:
        if db_name:
            conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{db_name}`;"))
            conn.commit()


def get_mysql_engine():
    return create_engine(os.getenv("MYSQL_URI"))


def run_migration_pipeline(db_name, collection_name):
    # Ensure MySQL database exists on RDS before attempting pipeline
    ensure_database_exists()

    # 1. Fetch sample data from MongoDB
    m_client = get_mongo_client()
    mongo_db = m_client[db_name]
    collection = mongo_db[collection_name]

    # Grab up to 5 documents to let LLM analyze structure thoroughly
    sample_docs = list(collection.find().limit(5))
    if not sample_docs:
        return (
            None,
            "No data found in the selected MongoDB collection to migrate.",
        )

    # Clean ObjectIds for text parsing
    for d in sample_docs:
        if "_id" in d:
            d["_id"] = str(d["_id"])

    # 2. Ask the LLM Agent to design the MySQL schema
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    schema_prompt = (
        "You are an expert data engineer. Analyze these sample JSON documents from a MongoDB collection:\n"
        "{docs_json}\n\n"
        "Your task is to design a strict MySQL relational table structure named '{table_name}' that accommodates this data structure.\n"
        "Flatten nested fields if necessary or convert objects/arrays into JSON strings or TEXT data types.\n\n"
        "CRITICAL RULES:\n"
        "1. Table Creation: Use `CREATE TABLE IF NOT EXISTS {table_name}`.\n"
        "2. Primary Key: You MUST map '_id' to column 'id' defined as `id VARCHAR(255) PRIMARY KEY`.\n"
        "3. Nullability: Do NOT add 'NOT NULL' constraints to non-essential fields.\n\n"
        "Return ONLY a raw JSON object containing two keys:\n"
        "1. 'create_table_sql': The exact DDL SQL string to create the table.\n"
        "2. 'field_mappings': A key-value mapping of MongoDB field keys to their intended MySQL column names.\n"
        "Do not wrap your response in markdown code blocks."
    )

    prompt = ChatPromptTemplate.from_template(schema_prompt)
    chain = prompt | llm

    response = chain.invoke(
        {
            "docs_json": json.dumps(sample_docs, default=str),
            "table_name": collection_name,
        }
    )

    # --- CLEANING LOGIC TO STRIP MARKDOWN WRAPPERS ---
    raw_content = response.content.strip()
    if raw_content.startswith("```"):
        lines = raw_content.splitlines()
        # Remove opening ``` or ```json
        if lines[0].startswith("```"):
            lines = lines[1:]
        # Remove closing ```
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        raw_content = "\n".join(lines).strip()

    try:
        migration_plan = json.loads(raw_content)
        create_sql = migration_plan["create_table_sql"]
        field_mappings = migration_plan["field_mappings"]
    except Exception as e:
        return (
            None,
            f"Failed parsing the AI migration plan: {str(e)}. Response was: {response.content}",
        )
    
    # 3. Execute Table Creation in MySQL
    sql_engine = get_mysql_engine()
    with sql_engine.begin() as conn:
        # Safely clear the old table first so the schema can update cleanly
        conn.execute(text(f"DROP TABLE IF EXISTS `{collection_name}`"))
        conn.execute(text(create_sql))

    # 4. Transform & Insert Data
    all_docs = list(collection.find())
    inserted_count = 0

    with sql_engine.begin() as conn:
        for doc in all_docs:
            row_data = {}
            for mongo_key, mysql_col in field_mappings.items():
                val = doc.get(mongo_key, None)

                # Ensure _id is stored as a clean plain string (Primary Key)
                if mongo_key == "_id":
                    val = str(val) if val is not None else None
                elif isinstance(val, (dict, list)):
                    val = json.dumps(val, default=str) if val is not None else None
                elif val is not None:
                    val = str(val)

                row_data[mysql_col] = val

            columns = ", ".join([f"`{k}`" for k in row_data.keys()])
            placeholders = ", ".join([f":{k}" for k in row_data.keys()])

            # REPLACE INTO will overwrite existing records matching the Primary Key, eliminating duplicates
            insert_query = text(
                f"REPLACE INTO `{collection_name}` ({columns}) VALUES ({placeholders})"
            )

            try:
                conn.execute(insert_query, row_data)
                inserted_count += 1
            except Exception as e:
                print(f"Skipped document ID {doc.get('_id')}: {e}")
                continue
            
    # 5. Execute Verification Query

    with sql_engine.connect() as conn:
        verify_query = f"SELECT * FROM `{collection_name}` LIMIT 10"
        results = conn.execute(text(verify_query))
        
        # Maps rows cleanly into dictionary representations
        columns = results.keys()
        preview_data = [dict(zip(columns, row)) for row in results]

    return {
        "table_name": collection_name,
        "ddl": create_sql,
        "count": inserted_count,
        "preview": preview_data,  # Passed to pd.DataFrame() in app.py
    }, None