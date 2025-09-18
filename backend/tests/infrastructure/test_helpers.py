"""Test helper functions for infrastructure tests."""
import logging
import asyncio
from typing import Any, List
from influxdb_client import InfluxDBClient

logger = logging.getLogger(__name__)

async def verify_influxdb_connection(client: InfluxDBClient) -> bool:
    """Verify connection to InfluxDB."""
    try:
        health = await client.ping()
        logger.info(f"InfluxDB connection health: {health}")
        return True
    except Exception as e:
        logger.error(f"Failed to connect to InfluxDB: {e}")
        return False

async def wait_for_data(
    client: InfluxDBClient,
    bucket: str,
    measurement: str,
    expected_count: int,
    max_retries: int = 5,
    retry_delay: int = 1
) -> List[Any]:
    """Wait for data to be available in InfluxDB with retries."""
    query = f'''
    from(bucket: "{bucket}")
        |> range(start: -1h)
        |> filter(fn: (r) => r._measurement == "{measurement}")
        |> count()
    '''
    
    for attempt in range(max_retries):
        try:
            logger.debug(f"Attempt {attempt + 1}/{max_retries} to fetch data")
            result = await client.query(query)
            
            if result and len(result) > 0 and result[0].get('_value', 0) >= expected_count:
                logger.info(f"Found {result[0].get('_value')} records, expected {expected_count}")
                return result
            
            logger.debug(f"Insufficient data found, waiting {retry_delay}s before retry")
            await asyncio.sleep(retry_delay)
            retry_delay *= 2
            
        except Exception as e:
            logger.error(f"Error querying data (attempt {attempt + 1}): {e}")
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(retry_delay)
            retry_delay *= 2
    
    return []

async def clean_bucket(client: InfluxDBClient, bucket: str) -> bool:
    """Clean all data from a bucket."""
    try:
        logger.info(f"Cleaning bucket: {bucket}")
        await client.delete_data(bucket, start="1970-01-01T00:00:00Z")
        await asyncio.sleep(1)  # Give time for deletion to process
        return True
    except Exception as e:
        logger.error(f"Failed to clean bucket {bucket}: {e}")
        return False
