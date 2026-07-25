import pandas as pd
import streamlit as st

from agent import execute_safe_query, generate_mongodb_query
from database import get_db_metadata
from migration_agent import run_migration_pipeline
from rag_router import build_schema_vector_store, get_relevant_schema

# --- Page Setup ---
st.set_page_config(page_title="MongoChat AI Agent", layout="wide")
st.title("🤖 MongoDB Agentic RAG Query System")

# --- Session State Initializations ---
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "vector_store" not in st.session_state:
    st.session_state.vector_store = None


# --- Helper Functions ---
def get_latest_scope1_output():
    """Retrieves the latest query results from Scope 1 chat history."""
    for message in reversed(st.session_state.chat_history):
        if message.get("role") == "assistant" and "results" in message:
            return message.get("results"), message.get("query")
    return None, None


# --- Sidebar Configuration ---
st.sidebar.header("🔌 Database Connection")
db_name = st.sidebar.text_input("Database Name", value="sample_mflix")

if st.sidebar.button("Index Database Schemas (RAG)"):
    with st.spinner("Fetching database schemas and building vector index..."):
        try:
            metadata = get_db_metadata(db_name)
            st.session_state.vector_store = build_schema_vector_store(metadata)
            st.sidebar.success(f"Successfully indexed {len(metadata)} collections!")
        except Exception as e:
            st.sidebar.error(f"Error: {e}")


# ==========================================
# SCOPE 1: AGENTIC RAG CHAT INTERFACE
# ==========================================
st.header("💬 Scope 1: Natural Language Querying")

if st.session_state.vector_store is None:
    st.info("Please index your database schema from the sidebar to begin.")
else:
    # Display Chat History
    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if "query" in message:
                st.code(message["query"], language="json")
            if "results" in message:
                st.json(message["results"])

    # User Input Chat Box
    if user_input := st.chat_input(
        "Ask a question (e.g., 'Find movies directed by Christopher Nolan')"
    ):

        # 1. Display user query
        with st.chat_message("user"):
            st.markdown(user_input)

        # 2. Process through Agent RAG Pipeline
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                coll_name, schema_context = get_relevant_schema(
                    st.session_state.vector_store, user_input
                )

                if not coll_name:
                    st.error("Could not determine a relevant collection for this query.")
                    st.stop()

                history_str = "\n".join(
                    [
                        f"{m['role']}: {m['content']}"
                        for m in st.session_state.chat_history[-4:]
                    ]
                )

                generated_mql = generate_mongodb_query(
                    user_input, coll_name, schema_context, history_str
                )

                st.markdown(f"**Identified Collection:** `{coll_name}`")
                st.markdown("**Generated Query:**")
                st.code(generated_mql, language="json")

                results, error = execute_safe_query(db_name, coll_name, generated_mql)

                if error:
                    st.error(f"Failed to execute query: {error}")
                    chat_entry = {
                        "role": "assistant",
                        "content": f"Failed to execute query: {error}",
                        "query": generated_mql,
                    }
                else:
                    st.markdown("**Results Found:**")
                    st.json(results)
                    chat_entry = {
                        "role": "assistant",
                        "content": f"I routed your query to the `{coll_name}` collection and fetched the results.",
                        "query": generated_mql,
                        "results": results,
                    }

                # Update history
                st.session_state.chat_history.append(
                    {"role": "user", "content": user_input}
                )
                st.session_state.chat_history.append(chat_entry)


# ==========================================
# SCOPE 2: TABULAR VIEW & MYSQL MIGRATION
# ==========================================
st.markdown("---")
st.header("📊 Scope 2: Interactive Data View & SQL Pipeline")

# 1. ALWAYS DISPLAY SCOPE 1 QUERY RESULTS IN TABULAR FORMAT
st.subheader("Scope 1 Query Results (Tabular)")
scope1_results, scope1_mql = get_latest_scope1_output()

if scope1_results:
    # Normalize nested JSON objects into a flat dataframe table
    scope1_df = pd.json_normalize(scope1_results)
    st.dataframe(scope1_df, use_container_width=True)

    with st.expander("🔍 View MQL Query Used"):
        st.code(scope1_mql, language="json")
else:
    st.info("💡 Run a query in Scope 1 above to display its tabular representation here.")


# 2. OPTIONAL MIGRATION PIPELINE
st.markdown("---")
with st.expander("🔄 Optional: Run NoSQL ➡️ MySQL Migration Pipeline"):
    col1, col2 = st.columns(2)
    with col1:
        source_collection = st.text_input(
            "Enter MongoDB Collection to Migrate", value="movies", key="migration_coll_input"
        )
    with col2:
        migrate_btn = st.button(
            "🚀 Execute MySQL Migration", use_container_width=True, key="migration_btn"
        )

    if migrate_btn:
        if st.session_state.vector_store is None:
            st.warning("Please index your database schema from the sidebar first.")
        else:
            with st.spinner(
                f"Migrating MongoDB collection (`{source_collection}`) to MySQL..."
            ):
                migration_result, error = run_migration_pipeline(
                    db_name, source_collection
                )

                if error:
                    st.error(error)
                else:
                    st.success(
                        f"Successfully migrated {migration_result['count']} documents!"
                    )
                    
                    st.markdown("#### Generated DDL Schema")
                    st.code(migration_result["ddl"], language="sql")

                    st.markdown(
                        f"#### Verification SQL Table: (`SELECT * FROM {migration_result['table_name']}`)"
                    )
                    mysql_df = pd.DataFrame(migration_result["preview"])
                    st.dataframe(mysql_df, use_container_width=True)