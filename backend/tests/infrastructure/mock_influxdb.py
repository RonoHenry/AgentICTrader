"""
Mock objects for InfluxDB testing.
"""
from unittest.mock import MagicMock

class MockInfluxDBClient:
    def __init__(self, url=None, token=None, org=None):
        self.url = url
        self.token = token
        self.org = org
        self.health_status = "pass"
        self.buckets = {}
        self._write_api = None
        self._query_api = None
        self._buckets_api = None
        
    def health(self):
        return MagicMock(status="pass")
    
    def write_api(self, write_options=None):
        if not self._write_api:
            self._write_api = MockWriteAPI(self)
        return self._write_api
        
    def query_api(self):
        if not self._query_api:
            self._query_api = MockQueryAPI(self)
        return self._query_api
        
    def buckets_api(self):
        if not self._buckets_api:
            self._buckets_api = MockBucketsAPI(self)
        return self._buckets_api
    
    def buckets_api(self):
        return MockBucketsAPI(self)

    def write_api(self, write_options=None):
        return MockWriteAPI(self)

    def query_api(self):
        return MockQueryAPI(self)

class MockBucketsAPI:
    def __init__(self, client):
        self.client = client
    
    def find_buckets(self):
        buckets = [
            MagicMock(
                id=f"mock-id-{name}",
                name=name, 
                retention_rules=rules,
                org_id=self.client.org
            )
            for name, rules in self.client.buckets.items()
        ]
        return MagicMock(buckets=buckets)
    
    def find_bucket_by_name(self, name):
        if name in self.client.buckets:
            return MagicMock(
                id=f"mock-id-{name}",
                name=name,
                retention_rules=self.client.buckets[name],
                org_id=self.client.org
            )
        return None
    
    def create_bucket(self, bucket_name, org=None):
        if bucket_name not in self.client.buckets:
            self.client.buckets[bucket_name] = []
        return MagicMock(
            id=f"mock-id-{bucket_name}",
            name=bucket_name,
            retention_rules=[],
            org_id=org or self.client.org
        )
    
    def update_bucket_retention_rules(self, bucket_id, rules):
        bucket_name = bucket_id.replace("mock-id-", "")
        if bucket_name in self.client.buckets:
            self.client.buckets[bucket_name] = rules

class MockWriteAPI:
    def __init__(self, client):
        self.client = client
        self.points = {}
    
    def write(self, bucket, org, record):
        if bucket not in self.points:
            self.points[bucket] = []
            
        # Ensure bucket exists
        buckets_api = self.client.buckets_api()
        if not buckets_api.find_bucket_by_name(bucket):
            buckets_api.create_bucket(bucket, org)
            
        if isinstance(record, dict):
            # Convert dict to proper point format if needed
            if 'measurement' not in record:
                record = {
                    'measurement': 'market_data',
                    'tags': {k: v for k, v in record.items() if isinstance(v, str)},
                    'fields': {k: v for k, v in record.items() if isinstance(v, (int, float))}
                }
        self.points[bucket].append(record)

class MockQueryAPI:
    def __init__(self, client):
        self.client = client
    
    def query(self, query, org):
        # Parse the bucket from the query
        try:
            import re
            bucket_match = re.search(r'bucket:\s*"([^"]+)"', query)
            if bucket_match:
                bucket = bucket_match.group(1)
                if bucket in self.client.write_api().points:
                    points = self.client.write_api().points[bucket]
                    if points:
                        # Create a mock record with the last point's values
                        return [MagicMock(
                            records=[
                                MagicMock(values={
                                    'measurement': points[-1].get('measurement', 'market_data'),
                                    **points[-1].get('tags', {}),
                                    **points[-1].get('fields', {})
                                })
                            ]
                        )]
        except Exception:
            pass
        return []
