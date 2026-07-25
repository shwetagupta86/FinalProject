# seed_data.py
import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

def seed_test_data():
    uri = os.getenv("MONGODB_URI")
    client = MongoClient(uri)
    
    # We will use 'sample_mflix' as the DB name so it matches our streamlit app default
    db = client["sample_mflix"]
    
    # 1. Create a 'movies' collection
    movies_coll = db["movies"]
    movies_coll.drop() # Clear if exists
    movies_coll.insert_many([
        {"title": "Inception", "director": "Christopher Nolan", "year": 2010, "genres": ["Sci-Fi", "Action"], "rating": 8.8},
        {"title": "Interstellar", "director": "Christopher Nolan", "year": 2014, "genres": ["Sci-Fi", "Drama"], "rating": 8.6},
        {"title": "The Dark Knight", "director": "Christopher Nolan", "year": 2008, "genres": ["Action", "Crime"], "rating": 9.0},
        {"title": "Pulp Fiction", "director": "Quentin Tarantino", "year": 1994, "genres": ["Crime", "Drama"], "rating": 8.9},
        {"title": "Avatar", "director": "James Cameron", "year": 2009, "genres": ["Action", "Sci-Fi"], "rating": 7.8}
    ])
    
    # 2. Create a 'users' collection
    users_coll = db["users"]
    users_coll.drop() # Clear if exists
    users_coll.insert_many([
        {"name": "Alice Smith", "email": "alice@example.com", "preferences": ["Sci-Fi", "Action"]},
        {"name": "Bob Jones", "email": "bob@example.com", "preferences": ["Crime"]}
    ])
    
    print("✅ Successfully seeded 'movies' and 'users' collections in 'sample_mflix'!")

if __name__ == "__main__":
    seed_test_data()