import asyncio
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import json
import os
import sys
import logging
import uvicorn


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger("PythonServer")

app = FastAPI(title="Python Backend Server")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


ORTHANC_URL = "http://localhost:8080"
USERNAME = "orthanc"
PASSWORD = "orthanc"

FILTERED_TAGS_FILE = "parameters.json"


TARGET_MEANINGS = [
    "Biparietal Diameter", "Head Circumference", "Abdominal Circumference",
    "Femur Length", "Cerebroplacental Ratio", "Umbilical Artery",
    "Trans Cerebellar Diameter", "Uterine", "Estimated Weight", "Amniotic Fluid Index",
    "Single Largest Vertical Pocket","nasal bone length","Nuchal Translucency","Intercranial Translucency","Pulsatility Index",
    "AMNIOTIC FLUID INDEX LEN q1","AMNIOTIC FLUID INDEX LEN q2",  "AMNIOTIC FLUID INDEX LEN q3", "AMNIOTIC FLUID INDEX LEN q4",
    "Crown Rump Length"
]

# Step 2: Create a listener for new instances
async def process_new_instance(instance_id):
    # Your existing process_new_instance function here
    print(f"Processing new instance with ID: {instance_id}")

async def listen_for_new_instances():
    last_instance_id = None
    while True:
        try:
            response = requests.get(f"{ORTHANC_URL}/instances", auth=(USERNAME, PASSWORD))
            if response.status_code == 200:
                instances = response.json()
                if instances:
                    if instances[-1] != last_instance_id:
                        last_instance_id = instances[-1]
                        print(f"New instance found! ID: {last_instance_id}")
                        await process_new_instance(last_instance_id)
                    else:
                        print("No new instances found.")
                else:
                    print("No instances available on the server.")
            else:
                print(f"Failed to fetch instances. Status code: {response.status_code}")
        except requests.RequestException as error:
            print(f"Error fetching instances: {error}")
        await asyncio.sleep(5)  # Wait for 5 seconds before next check


# Step 3: Download JSON file for new instance
async def process_new_instance(instance_id):
    try:
        response = requests.get(f"{ORTHANC_URL}/instances/{instance_id}/tags", auth=(USERNAME, PASSWORD))
        if response.status_code == 200:
            instance_data = response.json()
            with open(f"{instance_id}.json", "w") as f:
                json.dump(instance_data, f, indent=2)
            filter_tags(instance_id)
    except requests.RequestException as error:
        print(f"Error processing instance {instance_id}: {error}")

# Step 4: Filter tags and store in JSON format
def filter_tags(instance_id):

    
    def extract_dicom_values(data, target_meanings):
        results = {}
        def process_sequence(sequence):
            for item in sequence:
                # Check for CONTAINS relationship and NUM value type
                if (item.get("0040,a010", {}).get("Value") == "CONTAINS" and 
                    item.get("0040,a040", {}).get("Value") == "NUM"):
                    
                    # Check if this is a Pulsatility Index measurement
                    concept_name_seq = item.get("0040,a043", {}).get("Value", [])
                    for concept in concept_name_seq:
                        if concept.get("0008,0104", {}).get("Value") == "Pulsatility Index":
                            # Get the numeric value
                            measured_seq = item.get("0040,a300", {}).get("Value", [])
                            if measured_seq:
                                numeric_value = measured_seq[0].get("0040,a30a", {}).get("Value")
                            
                            # Look for associated Finding Site and Laterality in ContentSequence
                            content_seq = item.get("0040,a730", {}).get("Value", [])
                            for content in content_seq:
                                if content.get("0040,a168", {}).get("Value", []):
                                    for value in content.get("0040,a168", {}).get("Value", []):
                                        if value.get("0008,0104", {}).get("Value") == "Middle Cerebral Artery":
                                            # Look for Laterality
                                            laterality = None
                                            laterality_seq = content.get("0040,a730", {}).get("Value", [])
                                            for lat in laterality_seq:
                                                lat_value = lat.get("0040,a168", {}).get("Value", [{}])[0].get("0008,0104", {}).get("Value")
                                                if lat_value in ["Left", "Right"]:
                                                    laterality = lat_value
                                                    results["Middle Cerebral Artery"] = numeric_value
                                                    break


                if (item.get("0040,a010", {}).get("Value") == "CONTAINS" and 
                    item.get("0040,a040", {}).get("Value") == "NUM"):
                
                
                    concept_name_seq = item.get("0040,a043", {}).get("Value", [])
                    for concept in concept_name_seq:
                        if concept.get("0008,0104", {}).get("Value") == "Pulsatility Index":
                            # Get the numeric value
                            measured_seq = item.get("0040,a300", {}).get("Value", [])
                            if measured_seq:
                                numeric_value = measured_seq[0].get("0040,a30a", {}).get("Value")
                        
                        # Look for Ductus Venosus in ContentSequence
                            content_seq = item.get("0040,a730", {}).get("Value", [])
                            for content in content_seq:
                                if (content.get("0040,a168", {}).get("Value", []) and 
                                    content.get("0040,a168", {}).get("Value", [])[0].get("0008,0104", {}).get("Value") == "Ductus Venosus"):
                                    results["Ductus Venosus"] = numeric_value
                                                    
                                                
                code_meaning = None
                numeric_value = None
                laterality = None


                if "0040,a730" in item:
                    content_seq = item["0040,a730"].get("Value", [])
                    for sub_item in content_seq:
                        # Look for laterality in nested sequences
                        if "0040,a730" in sub_item:
                            for lat_item in sub_item["0040,a730"].get("Value", []):
                                if lat_item.get("0040,a043", {}).get("Value", [{}])[0].get("0008,0104", {}).get("Value") == "Laterality":
                                    lat_value = lat_item.get("0040,a168", {}).get("Value", [{}])[0].get("0008,0104", {}).get("Value")
                                    if lat_value in ["Left", "Right"]:
                                        laterality = lat_value

                # Extract CodeMeaning
                concept_name_seq = item.get("0040,a043", {}).get("Value", [])
                for concept in concept_name_seq:
                    code_meaning_data = concept.get("0008,0104", {})
                    if code_meaning_data.get("Name") == "CodeMeaning":
                        code_meaning = code_meaning_data.get("Value")
                         # If CodeMeaning is LMP, extract the associated date
                        if code_meaning == "LMP":
                            date_value = item.get("0040,a121", {}).get("Value")
                            if date_value:
                                results["LMP"] = date_value
                    
                        break


                # Extract NumericValue if CodeMeaning is in target list
                if code_meaning in target_meanings:
                    measured_value_seq = item.get("0040,a300", {}).get("Value", [])
                    for measured in measured_value_seq:
                        numeric_value_data = measured.get("0040,a30a", {})
                        if numeric_value_data.get("Name") == "NumericValue":
                            numeric_value = numeric_value_data.get("Value")
                            break



                    if numeric_value:
                        if code_meaning == "Pulsatility Index" and laterality:
                            key = f"{laterality} Uterine {code_meaning}"
                            results[key] = numeric_value

                             # Calculate mean if both Left and Right PI exist
                            left_pi = results.get("Left Uterine Pulsatility Index")
                            right_pi = results.get("Right Uterine Pulsatility Index")
                            if left_pi is not None and right_pi is not None:
                                mean_uta = (float(left_pi) + float(right_pi)) / 2
                                results["Uterine"] = str(round(mean_uta, 2))
                        else:
                            results[code_meaning] = numeric_value

                # Recursively process nested sequences
                for value in item.values():
                    if isinstance(value, dict) and value.get("Type") == "Sequence":
                        process_sequence(value.get("Value", []))

         # Start processing from the top level
        sequence = data.get("0040,a730", {}).get("Value", [])
        process_sequence(sequence)

        return results

    try:
        with open(f"{instance_id}.json", "r") as f:
            instance_data = json.load(f)
        
        extracted_data = extract_dicom_values(instance_data, TARGET_MEANINGS)
         # Find the highest AFI quadrant value
        afi_quadrants = []
        for i in range(1, 5):
            quadrant_key = f"AMNIOTIC FLUID INDEX LEN q{i}"
            if quadrant_key in extracted_data:
                try:
                    value = float(extracted_data[quadrant_key])
                    afi_quadrants.append(value)
                except (ValueError, TypeError):
                    continue
        
        # Set the highest value as Single Largest Vertical Pocket
        if afi_quadrants:
            extracted_data["Single Largest Vertical Pocket"] = str(max(afi_quadrants))
        
        extracted_data["PatientName"] = instance_data.get("0010,0010", {}).get("Value", "")
        extracted_data["PatientID"] = instance_data.get("0010,0020", {}).get("Value", "")
        extracted_data["PatientBirthDate"] = instance_data.get("0010,0030", {}).get("Value", "")
        
        
        with open(FILTERED_TAGS_FILE, "w") as f:
            json.dump(extracted_data, f, indent=2)
    except Exception as error:
        print(f"Error filtering tags for instance {instance_id}: {error}")


@app.get("/api/filtered_tags")
async def get_filtered_tags():
    logger.info("Root endpoint accessed")
    if os.path.exists(FILTERED_TAGS_FILE):
        with open(FILTERED_TAGS_FILE, "r") as f:
            return json.load(f)
    else:
        raise HTTPException(status_code=404, detail="Filtered tags not found")

@app.get("/")
async def home():
    return {"message": "Orthanc Listener is running"}

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(listen_for_new_instances())


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup function that runs when the server shuts down"""
    logger.info("Server shutting down - cleaning up files...")
    try:
        if os.path.exists(FILTERED_TAGS_FILE):
            os.remove(FILTERED_TAGS_FILE)
            logger.info(f"Successfully deleted {FILTERED_TAGS_FILE}")
    except Exception as e:
        logger.error(f"Error deleting {FILTERED_TAGS_FILE}: {str(e)}")

# Add signal handlers for graceful shutdown
def handle_exit(signum, frame):
    logger.info("Received shutdown signal")
    sys.exit(0)




if __name__ == "__main__":
    import signal
    # Register signal handlers
    signal.signal(signal.SIGINT, handle_exit)  # Handle Ctrl+C
    signal.signal(signal.SIGTERM, handle_exit)  # Handle termination

    logger.info("Starting Python server...")
    try:
        uvicorn.run(app, host="localhost", port=5001, log_level="info")
    except Exception as e:
        logger.error(f"Failed to start server: {str(e)}")
        sys.exit(1)