# Cisco Meraki AP Utilization Report

This project generates searchable HTML report including the most recent 5-minute snapshot of channel utilization and client count per band per access point in a selected Cisco Meraki Dashboard network.

## How to use
Generate your API key using Cisco Meraki Dashboard and save it to **token.txt** file in the same folder as the Python script. Save your Organization ID to **org.txt**.

Execute the the script using

```python3 meraki-ap-util.py```

## The mandatory boring legal part
This script is provided "AS IS" without warranty of any kind, express or implied.
The author assumes no responsibility for errors, omissions, or damages resulting 
from the use of this script. Use at your own risk.
