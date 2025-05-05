import requests
import json
from pathlib import Path
from typing import Dict, Optional
from mcp.server.fastmcp import FastMCP
import os
import sys
import traceback
from datetime import datetime, timedelta
from dotenv import load_dotenv
import asyncio
import netCDF4 as nc
import tempfile
# Load environment variables from .env file
load_dotenv()

def log_error(message: str):
    """Helper function to log errors to stderr with timestamp"""
    print(f"[ERROR] {message}", file=sys.stderr)

def log_info(message: str):
    """Helper function to log info to stderr with timestamp"""
    print(f"[INFO] {message}", file=sys.stderr)

# Log environment information
# log_info("=== Environment Information ===")
# log_info(f"Python version: {sys.version}")
# log_info(f"Current working directory: {os.getcwd()}")
# log_info(f"Absolute path: {Path.cwd().absolute()}")

# Initialize FastMCP server
try:
    print("Initializing MCP server...", file=sys.stderr)
    mcp = FastMCP("arm_livedata")
    log_info("MCP server initialized successfully")
except Exception as e:
    log_error(f"Failed to initialize MCP server: {str(e)}")
    log_error(f"Error type: {type(e).__name__}")
    log_error("Full traceback:")
    traceback.print_exc(file=sys.stderr)
    raise

# Constants
ARM_API_BASE = "https://adc.arm.gov/armlive/data"
USER_AGENT = "arm-live-data/1.0"

def get_credentials() -> tuple[str, str]:
    """Get ARM credentials from environment variables.
    
    Returns:
        Tuple of (username, api_token)
        
    Raises:
        ValueError if credentials are not properly set
    """
    username = os.getenv("ARM_USERNAME")
    api_token = os.getenv("ARM_API_TOKEN")
    
    if not username or not api_token:
        raise ValueError(
            "ARM credentials not found. Please set ARM_USERNAME and ARM_API_TOKEN environment variables "
            "or create a .env file with these values."
        )
    
    return username, api_token

@mcp.tool()
async def query_live_data(
    datastream: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
) -> Dict:
    """Query the ARM Live Data API for real-time data.
    
    Args:
        datastream: The datastream to query (required)
        start_time: Start time for data query (optional, defaults to 1 hour ago)
        end_time: End time for data query (optional, defaults to current time)
        
    Returns:
        Dict containing the live data
    """
    try:
        # Get credentials from environment
        username, api_token = get_credentials()
        log_info(f"Using credentials for user: {username}")
        
        # Set default time range if not provided
        if not start_time:
            start_time = (datetime.utcnow() - timedelta(hours=1)).strftime("%Y-%m-%d")
        else:
            # If start_time is a datetime object, convert it to string
            if isinstance(start_time, datetime):
                start_time = start_time.strftime("%Y-%m-%d")
            # If it's a string in YYYY-MM-DDThh:mm:ss format, extract just the date
            elif isinstance(start_time, str) and "T" in start_time:
                start_time = start_time.split("T")[0]
            # If it's already a string in YYYY-MM-DD format, use it as is
            elif isinstance(start_time, str) and len(start_time) == 10:
                start_time = start_time

        if not end_time:
            end_time = datetime.utcnow().strftime("%Y-%m-%d")
        else:
            # If end_time is a datetime object, convert it to string
            if isinstance(end_time, datetime):
                end_time = end_time.strftime("%Y-%m-%d")
            # If it's a string in YYYY-MM-DDThh:mm:ss format, extract just the date
            elif isinstance(end_time, str) and "T" in end_time:
                end_time = end_time.split("T")[0]
            # If it's already a string in YYYY-MM-DD format, use it as is
            elif isinstance(end_time, str) and len(end_time) == 10:
                end_time = end_time

        # Construct URL with correct format according to API docs
        # user must be first parameter, and we need wt=json for JSON response
        base_url = f"{ARM_API_BASE}/query"
        params = {
            "user": f"{username}:{api_token}",  # user must be first parameter
            "ds": datastream,
            "start": start_time,
            "end": end_time,
            "wt": "json"  # required for JSON response
        }
        
        log_info(f"Request URL: {base_url}")
        log_info(f"Request params: {params}")

        # Make API request with params
        response = requests.get(base_url, params=params)

        log_info(f"Response status code: {response.status_code}")
        log_info(f"Response headers: {dict(response.headers)}")

        if response.status_code == 200:
            try:
                data = response.json()
                log_info(f"Successfully retrieved data. Response size: {len(str(data))} bytes")
                return data
            except json.JSONDecodeError as e:
                log_error(f"Failed to parse JSON response: {str(e)}")
                log_error(f"Raw response: {response.text[:500]}...")  # Show first 500 chars of response
                raise
        elif response.status_code == 401:
            error_msg = "Authentication failed. Please check your ARM credentials."
            log_error(error_msg)
            log_error(f"Response text: {response.text}")
            raise Exception(error_msg)
        else:
            error_msg = f"Error fetching live data: {response.status_code}, {response.text}"
            log_error(error_msg)
            raise Exception(error_msg)

    except requests.exceptions.RequestException as e:
        log_error(f"Network error occurred: {str(e)}")
        raise Exception(f"Network error while querying ARM Live Data API: {str(e)}")
    except Exception as e:
        log_error(f"Unexpected error: {str(e)}")
        log_error("Full traceback:")
        traceback.print_exc(file=sys.stderr)
        raise Exception(f"Error querying ARM Live Data API: {str(e)}")


async def read_cdf_file(cdf_file: str) -> Dict:
    """Read data from a CDF file.
    
    Args:
        cdf_file: The name of the CDF file to read (e.g. 'nsametC1.b1.20200101.000000.cdf')
        
    Returns:
        Dict containing the CDF data with variables and their attributes
    """
    try:
        # Open the CDF file
        dataset = nc.Dataset(cdf_file, 'r')
        
        # Initialize result dictionary
        result = {'variables': {}}
        
        # Process each variable in the dataset
        for var_name, var in dataset.variables.items():
            # Get variable data and attributes
            var_data = var[:]
            var_attrs = {attr: var.getncattr(attr) for attr in var.ncattrs()}
            
            # Store variable data and attributes
            result['variables'][var_name] = {
                'data': var_data,
                **var_attrs
            }
        
        # Close the dataset
        dataset.close()
        
        log_info(f"Successfully read CDF file: {cdf_file}")
        return result
        
    except Exception as e:
        log_error(f"Error reading CDF file {cdf_file}: {str(e)}")
        log_error("Full traceback:")
        traceback.print_exc(file=sys.stderr)
        raise Exception(f"Error reading CDF file: {str(e)}")

@mcp.tool()
async def return_cdf_data(cdf_file: str, variable: str) -> Dict:
    """Download, read a CDF file from ARM Live Data API and return the data as a dictionary for further analysis.
    
    Args:
        cdf_file: The name of the CDF file to download (e.g. 'nsametC1.b1.20200101.000000.cdf')
        
    Returns:
        Data Array from the CDF file
    """
    try:
        # Get credentials from environment
        username, api_token = get_credentials()
        
        # Create a temporary directory to store the downloaded file
        with tempfile.TemporaryDirectory() as temp_dir:
            # Construct the saveData URL
            save_url = f"{ARM_API_BASE}/saveData"
            params = {
                "user": f"{username}:{api_token}",
                "file": cdf_file
            }
            
            log_info(f"Downloading CDF file: {cdf_file}")
            log_info(f"Request URL: {save_url}")
            log_info(f"Request params: {params}")
            
            # Download the file
            response = requests.get(save_url, params=params)
            
            if response.status_code == 200:
                # Save the file to temporary directory
                temp_file_path = os.path.join(temp_dir, cdf_file)
                with open(temp_file_path, 'wb') as f:
                    f.write(response.content)
                
                log_info(f"File downloaded successfully to: {temp_file_path}")
                
                try:
                    # Read the CDF file using our existing function
                    cdf_data = await read_cdf_file(temp_file_path)
                    return cdf_data["variables"][variable]["data"]
                finally:
                    # Ensure the temporary file is deleted after reading
                    try:
                        os.remove(temp_file_path)
                        log_info(f"Temporary file deleted: {temp_file_path}")
                    except Exception as e:
                        log_error(f"Error deleting temporary file: {str(e)}")
            else:
                error_msg = f"Error downloading CDF file: {response.status_code}, {response.text}"
                log_error(error_msg)
                raise Exception(error_msg)
                
    except Exception as e:
        log_error(f"Error in save_cdf_data: {str(e)}")
        log_error("Full traceback:")
        traceback.print_exc(file=sys.stderr)
        raise Exception(f"Error downloading and reading CDF file: {str(e)}")


if __name__ == '__main__':
    mcp.run("stdio") 
