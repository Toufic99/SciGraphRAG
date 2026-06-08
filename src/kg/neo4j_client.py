"""
neo4j_client.py

Simple wrapper around neo4j.Driver for basic query execution and batch import.
"""
from neo4j import GraphDatabase
import os
from dotenv import load_dotenv

load_dotenv()

class Neo4jClient:
    def __init__(self, uri=None, user=None, password=None):
        self.uri = uri or os.getenv('NEO4J_URI')
        self.user = user or os.getenv('NEO4J_USER')
        self.password = password or os.getenv('NEO4J_PASSWORD')
        self.driver = None

    def connect(self):
        if self.driver is None:
            self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
        return self.driver

    def close(self):
        if self.driver:
            self.driver.close()
            self.driver = None

    def run_query(self, cypher, params=None):
        self.connect()
        with self.driver.session() as session:
            return list(session.run(cypher, params or {}))

    def batch_import(self, cypher, data, batch_size=500):
        """Import using UNWIND pattern. cypher must accept $batch param and UNWIND it."""
        self.connect()
        with self.driver.session() as session:
            for i in range(0, len(data), batch_size):
                batch = data[i:i+batch_size]
                session.run(cypher, {'batch': batch})
