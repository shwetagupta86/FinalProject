# agent.py
import json
import bson
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from database import get_mongo_client

def generate_mongodb_query(user_prompt, collection_name, schema_context, history=""):
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    
    system_prompt = (
        "You are an expert MongoDB administrator and AI agent.\n"
        "Your task is to convert a natural language request into a valid MongoDB Query Language (MQL) JSON object.\n\n"
        "Target Collection: {collection_name}\n"
        "Collection Schema/Sample: {schema_context}\n\n"
        "Conversation History:\n{history}\n\n"
        "CRITICAL INSTRUCTIONS:\n"
        "1. Return ONLY a raw JSON object containing two keys: 'find_filter' (the query object) and 'projection' (optional fields to return, default empty dict {{}}).\n"
        "2. Do not wrap the JSON in markdown code blocks like ```json.\n"
        "3. Ensure the JSON is completely valid."
    )
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "{user_prompt}")
    ])
    
    chain = prompt | llm
    response = chain.invoke({
        "collection_name": collection_name,
        "schema_context": schema_context,
        "user_prompt": user_prompt,
        "history": history
    })
    
    return response.content.strip()

def execute_safe_query(db_name, collection_name, query_string):
    client = get_mongo_client()
    db = client[db_name]
    coll = db[collection_name]
    
    try:
        query_json = json.loads(query_string)
        filter_obj = query_json.get("find_filter", {})
        projection_obj = query_json.get("projection", {})
        
        # Execute query (limiting to 10 for safety/UI rendering)
        results = list(coll.find(filter_obj, projection_obj).limit(10))
        
        # Serialize BSON ObjectIds to string for Streamlit JSON viewer
        for doc in results:
            if '_id' in doc:
                doc['_id'] = str(doc['_id'])
        return results, None
    except Exception as e:
        return None, str(e)