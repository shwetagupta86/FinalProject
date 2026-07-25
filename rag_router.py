# rag_router.py
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document

def build_schema_vector_store(metadata):
    documents = []
    for coll_name, info in metadata.items():
        # Create a text representation of the collection for embedding
        content = f"Collection Name: {coll_name}\nDescription: {info['description']}\nSchema Sample: {info['sample_schema']}"
        doc = Document(page_content=content, metadata={"collection_name": coll_name, "schema": str(info['sample_schema'])})
        documents.append(doc)
    
    embeddings = OpenAIEmbeddings()
    vector_store = FAISS.from_documents(documents, embeddings)
    return vector_store

def get_relevant_schema(vector_store, user_query):
    # Retrieve the top most relevant collection schema
    docs = vector_store.similarity_search(user_query, k=1)
    if docs:
        return docs[0].metadata["collection_name"], docs[0].metadata["schema"]
    return None, None