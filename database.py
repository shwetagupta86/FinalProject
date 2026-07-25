import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

def get_mongo_client():
    uri = os.getenv("MONGODB_URI")
    return MongoClient(uri)

def get_db_metadata(db_name):
    client = get_mongo_client()
    db = client[db_name]
    
    metadata = {}
    for collection_name in db.list_collection_names():
        # Fetch a sample document to understand the schema structure
        sample_doc = db[collection_name].find_one()
        # Clean up ObjectId for string representation if needed
        if sample_doc and '_id' in sample_doc:
            sample_doc['_id'] = str(sample_doc['_id'])
            
        metadata[collection_name] = {
            "description": f"Contains data related to {collection_name}.",
            "sample_schema": sample_doc
        }
    return metadata