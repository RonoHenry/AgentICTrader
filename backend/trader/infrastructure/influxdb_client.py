"""
InfluxDB client wrapper for market data storage.
"""
import logging
import asyncio
from typing import List, Optional, Dict, Any
from influxdb_client import InfluxDBClient as BaseInfluxDBClient
from influxdb_client import Point, WriteOptions

logger = logging.getLogger(__name__)

class InfluxDBClient:
    """Wrapper for InfluxDB client with async support."""
    
    def __init__(
        self,
        url: str,
        token: str,
        org: str,
        debug: bool = False
    ):
        """Initialize the client."""
        self.url = url
        self.token = token
        self.org = org
        self.debug = debug
        self.client = BaseInfluxDBClient(
            url=url,
            token=token,
            org=org,
            debug=debug
        )
        
        # Configure write options for reliable testing
        write_options = WriteOptions(
            batch_size=1,  # Write each point immediately
            flush_interval=1_000,  # Flush frequently
            write_type=2,  # Synchronous writes
            max_retries=3,
            retry_interval=1_000,
            max_retry_delay=5_000,
            exponential_base=2
        )
        
        self.write_api = self.client.write_api(write_options=write_options)
        self.query_api = self.client.query_api()
        self._buckets_api = self.client.buckets_api()
        self._delete_api = self.client.delete_api()
    
    async def write(self, bucket: str, points: List[Point]):
        """Write points to InfluxDB."""
        if not points:
            logger.debug("No points to write")
            return
            
        try:
            # Ensure bucket exists
            bucket_exists = False
            try:
                bucket_exists = bool(self._buckets_api.find_bucket_by_name(bucket))
            except Exception as e:
                logger.warning(f"Error checking bucket existence: {e}")
            
            if not bucket_exists:
                logger.debug(f"Creating bucket {bucket}")
                try:
                    self._buckets_api.create_bucket(bucket_name=bucket, org=self.org)
                except Exception as e:
                    if "already exists" not in str(e).lower():
                        raise
            
            # Convert single point to list
            points_list = [points] if not isinstance(points, (list, tuple)) else points
            
            # Write points with batching and retry logic
            for i in range(0, len(points_list), 100):  # Process in chunks of 100
                batch = points_list[i:i+100]
                logger.debug(f"Writing batch of {len(batch)} points to bucket {bucket}")
                
                # Write with retries
                max_retries = 3
                retry_delay = 1
                
                for attempt in range(max_retries):
                    try:
                        self.write_api.write(bucket=bucket, record=batch, write_precision='ns')
                        self.write_api.flush()  # Ensure the batch is written
                        break
                    except Exception as e:
                        if attempt == max_retries - 1:
                            raise
                        logger.warning(f"Write attempt {attempt + 1} failed: {e}")
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2
            
            logger.debug(f"Successfully wrote {len(points_list)} points")
            
        except Exception as e:
            logger.error(f"Error writing to InfluxDB: {e}")
            raise
    
    async def query(self, query: str) -> List[Dict[str, Any]]:
        """Execute a Flux query with retries."""
        max_retries = 3
        retry_delay = 1
        last_error = None
        
        for attempt in range(max_retries):
            try:
                logger.debug(f"Executing query (attempt {attempt + 1}): {query}")
                tables = self.query_api.query(query)
                results = []
                
                for table in tables:
                    for record in table.records:
                        result = {}
                        
                        # Add all values including fields and tags
                        result.update(record.values)
                        
                        # Add measurement name
                        try:
                            measurement = record.get_measurement()
                            if measurement:
                                result["_measurement"] = measurement
                        except Exception as e:
                            logger.debug(f"Could not get measurement: {e}")
                        
                        # Add field value and name
                        try:
                            value = record.get_value()
                            if value is not None:
                                result["_value"] = value
                        except Exception as e:
                            logger.debug(f"Could not get value: {e}")
                        
                        try:
                            field = record.get_field()
                            if field is not None:
                                result["_field"] = field
                        except Exception as e:
                            logger.debug(f"Could not get field: {e}")
                        
                        # Add time safely
                        try:
                            time = record.get_time()
                            if time:
                                result["_time"] = time
                        except Exception as e:
                            logger.debug(f"Could not get time: {e}")
                        
                        results.append(result)
                
                logger.debug(f"Query returned {len(results)} results")
                return results
                
            except Exception as e:
                last_error = e
                if attempt == max_retries - 1:
                    logger.error(f"Query failed after {max_retries} attempts: {e}")
                    raise
                
                logger.warning(f"Query attempt {attempt + 1} failed: {e}")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
        
        raise last_error if last_error else Exception("Query failed with unknown error")
    
    def ping(self) -> bool:
        """Test connection to InfluxDB."""
        try:
            return self.client.ping()
        except Exception as e:
            logger.error(f"Error pinging InfluxDB: {e}")
            return False
    
    async def delete_data(self, bucket: str, start: str, stop: Optional[str] = None, measurement: Optional[str] = None):
        """Delete data from a bucket within a time range."""
        try:
            logger.debug(f"Deleting data from bucket {bucket} starting at {start}")
            if stop is None:
                # If no stop time is provided, use a far future date
                stop = "2030-12-31T23:59:59Z"
                
            if measurement:
                # Delete specific measurement
                predicate = f'_measurement="{measurement}"'
            else:
                # Delete all measurements
                predicate = '_measurement != ""'
                
            self._delete_api.delete(start=start, stop=stop, predicate=predicate, bucket=bucket)
            logger.debug(f"Delete operation completed for {'measurement ' + measurement if measurement else 'all data'}")
        except Exception as e:
            logger.error(f"Error deleting data from InfluxDB: {e}")
            raise
    
    def buckets_api(self):
        """Get the buckets API client."""
        return self._buckets_api
    
    def close(self):
        """Close the client connection."""
        try:
            self.write_api.flush()  # Ensure all pending writes are completed
            self.write_api.close()
            self.client.close()
        except Exception as e:
            logger.error(f"Error closing InfluxDB client: {e}")
            raise
