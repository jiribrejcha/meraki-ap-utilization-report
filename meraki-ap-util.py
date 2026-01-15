"""
Cisco Meraki AP Utilization Monitor

This script is provided "AS IS" without warranty of any kind, express or implied.
The author assumes no responsibility for errors, omissions, or damages resulting 
from the use of this script. Use at your own risk.

Author: Jiri Brejcha (jibrejch@cisco.com)
"""

import requests
import html
import time
from datetime import datetime
import hashlib
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
import webbrowser
import os
import sys

def read_file(filename):
    try:
        with open(filename, 'r') as file:
            content = file.read().strip().replace('\n', '').replace('\r', '')
            return content if content else None
    except FileNotFoundError:
        return None

def get_networks(org_id, api_key):
    url = f"https://api.meraki.com/api/v1/organizations/{org_id}/networks"
    headers = {
        "X-Cisco-Meraki-API-Key": api_key,
        "Accept": "application/json"
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()

def get_device_names(org_id, api_key, network_id):
    url = f"https://api.meraki.com/api/v1/networks/{network_id}/devices"
    headers = {
        "X-Cisco-Meraki-API-Key": api_key,
        "Accept": "application/json"
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    devices = response.json()
    device_map = {}
    for device in devices:
        serial = device.get("serial")
        name = device.get("name")
        if serial:
            device_map[serial] = name if name else "Default Device Name"
    return device_map

def get_device_models(org_id, api_key, network_id):
    url = f"https://api.meraki.com/api/v1/networks/{network_id}/devices"
    headers = {
        "X-Cisco-Meraki-API-Key": api_key,
        "Accept": "application/json"
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    devices = response.json()
    model_map = {}
    for device in devices:
        serial = device.get("serial")
        model = device.get("model")
        if serial:
            model_map[serial] = model if model else "Unknown Model"
    return model_map

def get_all_wireless_devices(org_id, api_key, network_id, device_names_map):
    """Get all wireless device statuses (online and offline)"""
    url = f"https://api.meraki.com/api/v1/organizations/{org_id}/devices/statuses"
    headers = {
        "X-Cisco-Meraki-API-Key": api_key,
        "Accept": "application/json"
    }
    params = {
        "networkIds[]": network_id
    }
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    statuses = response.json()
    
    # Return dictionaries of online and offline wireless devices
    online_wireless_serials = set()
    offline_wireless_devices = {}
    
    for device in statuses:
        serial = device.get("serial")
        status = device.get("status")
        product_type = device.get("productType", "")
        device_name = device_names_map.get(serial, "Unknown")
        
        # Check if device is wireless
        if product_type.startswith("wireless"):
            if status == "online":
                online_wireless_serials.add(serial)
                print(f"  ✓ {device_name} ({serial}) - ONLINE")
            else:
                offline_wireless_devices[serial] = status if status else "offline"
                print(f"  ✗ {device_name} ({serial}) - {status.upper() if status else 'OFFLINE'}")
    
    return online_wireless_serials, offline_wireless_devices

def get_channel_utilization_per_band(api_key, network_id, serials):
    """Get channel utilization per band for each AP using channelUtilizationHistory"""
    utilization_map = {}
    headers = {
        "X-Cisco-Meraki-API-Key": api_key,
        "Accept": "application/json"
    }
    
    # Calculate t0 and t1 (last 10 minutes)
    from datetime import datetime, timedelta, timezone
    t1 = datetime.now(timezone.utc)
    t0 = t1 - timedelta(minutes=10)
    t0_str = t0.strftime("%Y-%m-%dT%H:%M:%SZ")
    t1_str = t1.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    for serial in serials:
        band_utilization = {"2.4": 0, "5": 0, "6": 0}
        
        # Query each band separately
        for band in ["2.4", "5", "6"]:
            try:
                url = f"https://api.meraki.com/api/v1/networks/{network_id}/wireless/channelUtilizationHistory"
                params = {
                    "t0": t0_str,
                    "t1": t1_str,
                    "autoResolution": "true",
                    "deviceSerial": serial,
                    "band": band
                }
                response = requests.get(url, headers=headers, params=params)
                response.raise_for_status()
                data = response.json()
                
                # Extract utilization from the most recent data point
                if data and isinstance(data, list) and len(data) > 0:
                    # Get the last (most recent) data point
                    most_recent = data[-1]
                    # The utilization might be in different fields, check common ones
                    utilization = most_recent.get("utilization", most_recent.get("utilizationTotal", 0))
                    band_utilization[band] = utilization if utilization is not None else 0
                    
            except requests.HTTPError as e:
                # Some APs may not support certain bands (e.g., 6 GHz)
                if e.response.status_code != 400:
                    print(f"Warning: HTTP error for {serial} band {band} utilization: {e}")
            except Exception as e:
                print(f"Warning: Error fetching band {band} utilization for {serial}: {e}")
        
        utilization_map[serial] = band_utilization
    
    return utilization_map

def get_wireless_connection_stats(api_key, network_id, serials):
    """Get wireless client counts per band for each AP using clientCountHistory with deviceSerial and band filter"""
    connection_stats_map = {}
    headers = {
        "X-Cisco-Meraki-API-Key": api_key,
        "Accept": "application/json"
    }
    
    # Calculate t0 and t1 (last 10 minutes)
    from datetime import datetime, timedelta, timezone
    t1 = datetime.now(timezone.utc)
    t0 = t1 - timedelta(minutes=10)
    t0_str = t0.strftime("%Y-%m-%dT%H:%M:%SZ")
    t1_str = t1.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    for serial in serials:
        band_clients = {"2.4": 0, "5": 0, "6": 0}
        
        # Query each band separately
        for band in ["2.4", "5", "6"]:
            try:
                url = f"https://api.meraki.com/api/v1/networks/{network_id}/wireless/clientCountHistory"
                params = {
                    "t0": t0_str,
                    "t1": t1_str,
                    "resolution": 300,
                    "deviceSerial": serial,
                    "band": band
                }
                response = requests.get(url, headers=headers, params=params)
                response.raise_for_status()
                data = response.json()
                
                # The API returns a list of data points directly when filtering by deviceSerial
                # No need to loop through entries - the data IS the list of data points
                if data and isinstance(data, list) and len(data) > 0:
                    # Get the last (most recent) data point
                    most_recent = data[-1]
                    client_count = most_recent.get("clientCount", 0)
                    band_clients[band] = client_count if client_count is not None else 0
                    
            except requests.HTTPError as e:
                # Some APs may not support certain bands (e.g., 6 GHz)
                if e.response.status_code != 400:
                    print(f"Warning: HTTP error for {serial} band {band}: {e}")
            except Exception as e:
                print(f"Warning: Error fetching band {band} stats for {serial}: {e}")
        
        connection_stats_map[serial] = band_clients
    
    return connection_stats_map

# Global variable to store the current version
current_page_version = {"version": "0"}

def generate_html_report(online_serials, offline_devices, device_names_map, device_models_map, network_name, connection_stats_map, utilization_per_band_map, last_updated):
    # Prepare rows with required data and determine row color
    rows = []
    
    # Process online devices
    for serial in online_serials:
        device_name = device_names_map.get(serial, "Default Device Name")
        device_model = device_models_map.get(serial, "Unknown Model")
        
        # Ensure we have strings, not None
        if device_name is None:
            device_name = "Default Device Name"
        if device_model is None:
            device_model = "Unknown Model"
        
        # Get per-band client counts from connection stats
        band_clients = connection_stats_map.get(serial, {"2.4": 0, "5": 0, "6": 0})
        
        # Calculate total clients by summing up all band clients (ensure no None values)
        client_24 = band_clients.get("2.4", 0)
        client_5 = band_clients.get("5", 0)
        client_6 = band_clients.get("6", 0)
        
        # Convert None to 0
        client_24 = 0 if client_24 is None else client_24
        client_5 = 0 if client_5 is None else client_5
        client_6 = 0 if client_6 is None else client_6
        
        total_clients = client_24 + client_5 + client_6
        
        # Get per-band utilization from channelUtilizationHistory
        band_utilization = utilization_per_band_map.get(serial, {"2.4": 0, "5": 0, "6": 0})
        
        band_info_map = {"2.4": {"util": 0, "clients": 0},
                         "5": {"util": 0, "clients": 0},
                         "6": {"util": 0, "clients": 0}}

        for band in ["2.4", "5", "6"]:
            # Use the utilization from channelUtilizationHistory, ensure it's a number
            util = band_utilization.get(band, 0)
            if util is None:
                util = 0
            # Use the client count from connection stats, ensure it's an integer
            clients = band_clients.get(band, 0)
            if clients is None:
                clients = 0
            band_info_map[band]["util"] = util
            band_info_map[band]["clients"] = clients

        # Determine row color based on per-band clients and utilization thresholds
        row_color = ""
        # Check for red condition: any band has > 100 clients OR any band util > 70%
        if any(band_info_map[band]["clients"] > 100 or band_info_map[band]["util"] > 70 for band in band_info_map):
            row_color = "style='background-color: red;'"
        # Check for orange condition: any band has > 50 clients OR any band util > 50%
        elif any(band_info_map[band]["clients"] > 50 or band_info_map[band]["util"] > 50 for band in band_info_map):
            row_color = "style='background-color: orange;'"

        rows.append({
            "device_name": html.escape(device_name),
            "device_model": html.escape(device_model),
            "total_clients": total_clients,
            "util_24": band_info_map["2.4"]["util"],
            "clients_24": band_info_map["2.4"]["clients"],
            "util_5": band_info_map["5"]["util"],
            "clients_5": band_info_map["5"]["clients"],
            "util_6": band_info_map["6"]["util"],
            "clients_6": band_info_map["6"]["clients"],
            "row_color": row_color,
            "is_offline": False,
            "status": "online"
        })
    
    # Process offline devices
    for serial, status in offline_devices.items():
        device_name = device_names_map.get(serial, "Default Device Name")
        device_model = device_models_map.get(serial, "Unknown Model")
        
        # Ensure we have strings, not None
        if device_name is None:
            device_name = "Default Device Name"
        if device_model is None:
            device_model = "Unknown Model"
        if status is None:
            status = "offline"
        
        rows.append({
            "device_name": html.escape(device_name),
            "device_model": html.escape(device_model),
            "total_clients": "-",
            "util_24": "-",
            "clients_24": "-",
            "util_5": "-",
            "clients_5": "-",
            "util_6": "-",
            "clients_6": "-",
            "row_color": "",
            "is_offline": True,
            "status": status
        })

    # Sort rows: online devices by 5 GHz utilization (descending), then offline devices
    online_rows = [r for r in rows if not r["is_offline"]]
    offline_rows = [r for r in rows if r["is_offline"]]
    
    online_rows.sort(key=lambda x: x["util_5"] if isinstance(x["util_5"], (int, float)) else 0, reverse=True)
    offline_rows.sort(key=lambda x: x["device_name"])
    
    rows = online_rows + offline_rows
    
    # Calculate total count for initial display
    total_count = len(rows)

    # Generate a unique version ID and update global variable
    version_string = f"{last_updated}_{len(rows)}"
    version_id = hashlib.md5(version_string.encode()).hexdigest()[:12]
    current_page_version["version"] = version_id

    # Build the HTML
    html_parts = []
    
    # HTML header
    html_parts.append('''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Cisco Meraki AP Utilization</title>
<style>
  * {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
  }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', sans-serif;
    background-color: #f6f6f6;
    padding: 20px;
    color: #333;
  }
  .container {
    max-width: 1400px;
    margin: 0 auto;
    background-color: white;
    border-radius: 8px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    overflow: hidden;
  }
  .header {
    background: linear-gradient(135deg, #143052 0%, #143052 100%);
    color: white;
    padding: 30px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .header h1 {
    font-size: 28px;
    font-weight: 600;
  }
  .header-info {
    text-align: right;
    font-size: 13px;
    opacity: 0.9;
  }
  .header-info p {
    margin: 4px 0;
  }
  .search-container {
    padding: 20px;
    background-color: #f8f9fa;
    border-bottom: 1px solid #e1e4e8;
    display: flex;
    align-items: center;
    gap: 10px;
    justify-content: space-between;
  }
  .search-left {
    display: flex;
    align-items: center;
    gap: 10px;
    flex: 1;
  }
  .search-right {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .search-input {
    width: 250px;
    padding: 10px 15px;
    border: 2px solid #e1e4e8;
    border-radius: 6px;
    font-size: 14px;
    transition: border-color 0.2s;
  }
  .search-input:focus {
    outline: none;
    border-color: #143052;
  }
  .clear-button {
    padding: 10px 20px;
    background-color: #6c757d;
    color: white;
    border: none;
    border-radius: 6px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    transition: background-color 0.2s;
  }
  .clear-button:hover {
    background-color: #5a6268;
  }
  .search-results {
    margin-left: 15px;
    font-size: 13px;
    color: #666;
  }
  .checkbox-container {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 14px;
    color: #555;
    cursor: pointer;
    user-select: none;
  }
  .checkbox-container input[type="checkbox"] {
    width: 18px;
    height: 18px;
    cursor: pointer;
  }
  .table-container {
    padding: 20px;
    overflow-x: auto;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 14px;
  }
  thead {
    background-color: #f8f9fa;
    border-bottom: 2px solid #e1e4e8;
  }
  th {
    padding: 16px 12px;
    text-align: left;
    font-weight: 600;
    color: #555;
    cursor: pointer;
    user-select: none;
    white-space: nowrap;
    transition: background-color 0.2s;
  }
  th:hover {
    background-color: #e9ecef;
  }
  td {
    padding: 14px 12px;
    border-bottom: 1px solid #e1e4e8;
    text-align: left;
  }
  .band-separator {
    border-right: 2px solid #143052 !important;
  }
  tbody tr {
    transition: background-color 0.15s;
  }
  tbody tr:hover {
    background-color: #f8f9fa;
  }
  tbody tr.hidden {
    display: none;
  }
  .ap-name {
    font-weight: 500;
    color: #2c3e50;
  }
  .model {
    color: #2c3e50;
    font-size: 13px;
  }
  .metric {
    font-weight: 500;
    text-align: center;
  }
  .status-red {
    background-color: #ff6b6b !important;
    color: white !important;
  }
  .status-red:hover {
    background-color: #ff5252 !important;
  }
  .status-orange {
    background-color: #ffa94d !important;
    color: white !important;
  }
  .status-orange:hover {
    background-color: #ff9933 !important;
  }
  .status-offline {
    background-color: #e9ecef !important;
    color: #6c757d !important;
  }
  .status-offline:hover {
    background-color: #dee2e6 !important;
  }
  .badge {
    display: inline-block;
    padding: 4px 10px;
    border-radius: 12px;
    font-size: 12px;
    font-weight: 600;
  }
  .badge-green {
    background-color: #d4edda;
    color: #155724;
  }
  .badge-gray {
    background-color: #e9ecef;
    color: #6c757d;
  }
  .sort-indicator {
    margin-left: 5px;
    opacity: 0.3;
    font-size: 10px;
  }
  .footer {
    background-color: #f8f9fa;
    padding: 20px;
    text-align: center;
    font-size: 12px;
    color: #666;
    border-top: 1px solid #e1e4e8;
  }
  .footer p {
    margin: 4px 0;
  }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>Cisco Meraki AP Utilization</h1>
    <div class="header-info">
      <p>Network: ''' + html.escape(network_name) + '''</p>
      <p>Last Updated: ''' + last_updated + '''</p>
    </div>
  </div>
  <div class="search-container">
    <div class="search-left">
      <input type="text" id="searchInput" class="search-input" placeholder="Search by AP name" oninput="searchTable()">
      <button class="clear-button" onclick="clearSearch()">Clear</button>
      <span id="searchResults" class="search-results">Showing ''' + str(total_count) + ''' access points</span>
    </div>
    <div class="search-right">
      <label class="checkbox-container">
        <input type="checkbox" id="hideOfflineCheckbox" onchange="toggleOfflineAPs()">
        <span>Hide offline APs</span>
      </label>
    </div>
  </div>
  <div class="table-container">
    <table id="apTable">
      <thead>
        <tr>
          <th onclick="sortTable(0)">Access Point <span class="sort-indicator">▼</span></th>
          <th onclick="sortTable(1)">Model <span class="sort-indicator">▼</span></th>
          <th onclick="sortTable(2)" class="metric band-separator">Clients <span class="sort-indicator">▼</span></th>
          <th onclick="sortTable(3)" class="metric">2.4 GHz Util [%] <span class="sort-indicator">▼</span></th>
          <th onclick="sortTable(4)" class="metric band-separator">2.4 GHz Clients <span class="sort-indicator">▼</span></th>
          <th onclick="sortTable(5)" class="metric">5 GHz Util [%] <span class="sort-indicator">▼</span></th>
          <th onclick="sortTable(6)" class="metric band-separator">5 GHz Clients <span class="sort-indicator">▼</span></th>
          <th onclick="sortTable(7)" class="metric">6 GHz Util [%] <span class="sort-indicator">▼</span></th>
          <th onclick="sortTable(8)" class="metric band-separator">6 GHz Clients <span class="sort-indicator">▼</span></th>
        </tr>
      </thead>
      <tbody id="tableBody">
''')

    # Table rows
    for row in rows:
        row_class = ""
        data_offline = ""
        
        if row["is_offline"]:
            row_class = 'class="status-offline"'
            data_offline = 'data-offline="true"'
            # For offline devices, show status badge
            status_display = f'<span class="badge badge-gray">{row["status"].upper()}</span>'
        else:
            data_offline = 'data-offline="false"'
            # Online device - apply color coding
            if "red" in row['row_color']:
                row_class = 'class="status-red"'
            elif "orange" in row['row_color']:
                row_class = 'class="status-orange"'
            status_display = f'<span class="badge badge-green">{row["total_clients"]}</span>'
        
        html_parts.append(f"<tr {row_class} {data_offline}>\n")
        html_parts.append(f"<td class='ap-name'>{row['device_name']}</td>\n")
        html_parts.append(f"<td class='model'>{row['device_model']}</td>\n")
        html_parts.append(f"<td class='metric band-separator'>{status_display}</td>\n")
        html_parts.append(f"<td class='metric'>{row['util_24']}</td>\n")
        html_parts.append(f"<td class='metric band-separator'>{row['clients_24']}</td>\n")
        html_parts.append(f"<td class='metric'>{row['util_5']}</td>\n")
        html_parts.append(f"<td class='metric band-separator'>{row['clients_5']}</td>\n")
        html_parts.append(f"<td class='metric'>{row['util_6']}</td>\n")
        html_parts.append(f"<td class='metric band-separator'>{row['clients_6']}</td>\n")
        html_parts.append("</tr>\n")

    # Footer and JavaScript
    html_parts.append('''
      </tbody>
    </table>
  </div>
  <div class="footer">
    <p>This page automatically refreshes every 60 seconds. Client count and channel utilization shows data for the past 5 minutes.</p>
    <p>Vibe coded by Jiri Brejcha (jibrejch@cisco.com). Blame Jiri for bugs, not Cisco.</p>
  </div>
</div>

<script>
var currentSortColumn = -1;
var currentSortDirection = "asc";
var currentVersion = null;

function checkForUpdates() {
  fetch("/version?t=" + new Date().getTime())
    .then(function(response) {
      return response.text();
    })
    .then(function(newVersion) {
      if (currentVersion === null) {
        currentVersion = newVersion;
        console.log("Initial version:", currentVersion);
      } else if (newVersion !== currentVersion) {
        console.log("Version changed from", currentVersion, "to", newVersion, "- reloading");
        location.reload(true);
      }
    })
    .catch(function(error) {
      console.error("Error checking for updates:", error);
    });
}

setInterval(checkForUpdates, 3000);

function sortTable(columnIndex) {
  var tbody = document.getElementById("tableBody");
  var rowsArray = Array.prototype.slice.call(tbody.rows);
  
  if (currentSortColumn === columnIndex) {
    currentSortDirection = currentSortDirection === "asc" ? "desc" : "asc";
  } else {
    currentSortDirection = "desc";
    currentSortColumn = columnIndex;
  }
  
  rowsArray.sort(function(rowA, rowB) {
    var aValue = rowA.cells[columnIndex].textContent.trim();
    var bValue = rowB.cells[columnIndex].textContent.trim();
    
    var aNum = parseFloat(aValue);
    var bNum = parseFloat(bValue);
    
    var comparison = 0;
    
    if (!isNaN(aNum) && !isNaN(bNum)) {
      comparison = aNum - bNum;
    } else {
      comparison = aValue.localeCompare(bValue);
    }
    
    return currentSortDirection === "asc" ? comparison : -comparison;
  });
  
  while (tbody.firstChild) {
    tbody.removeChild(tbody.firstChild);
  }
  
  for (var i = 0; i < rowsArray.length; i++) {
    tbody.appendChild(rowsArray[i]);
  }
  
  updateSortIndicators(columnIndex);
}

function updateSortIndicators(columnIndex) {
  var headers = document.querySelectorAll("#apTable th");
  for (var i = 0; i < headers.length; i++) {
    var indicator = headers[i].querySelector(".sort-indicator");
    if (indicator) {
      if (i === columnIndex) {
        indicator.textContent = currentSortDirection === "asc" ? "▲" : "▼";
        indicator.style.opacity = "1";
      } else {
        indicator.textContent = "▼";
        indicator.style.opacity = "0.3";
      }
    }
  }
}

function toggleOfflineAPs() {
  var checkbox = document.getElementById("hideOfflineCheckbox");
  var tbody = document.getElementById("tableBody");
  var rows = tbody.getElementsByTagName("tr");
  
  for (var i = 0; i < rows.length; i++) {
    var isOffline = rows[i].getAttribute("data-offline") === "true";
    if (isOffline) {
      if (checkbox.checked) {
        rows[i].style.display = "none";
      } else {
        rows[i].style.display = "";
      }
    }
  }
  
  updateResultsCount();
}

function searchTable() {
  var input = document.getElementById("searchInput");
  var filter = input.value.toLowerCase().trim();
  var tbody = document.getElementById("tableBody");
  var rows = tbody.getElementsByTagName("tr");
  
  for (var i = 0; i < rows.length; i++) {
    var apNameCell = rows[i].getElementsByTagName("td")[0];
    if (apNameCell) {
      var apName = apNameCell.textContent || apNameCell.innerText;
      if (filter === "" || apName.toLowerCase().indexOf(filter) > -1) {
        rows[i].classList.remove("hidden");
      } else {
        rows[i].classList.add("hidden");
      }
    }
  }
  
  updateResultsCount();
}

function updateResultsCount() {
  var input = document.getElementById("searchInput");
  var filter = input.value.toLowerCase().trim();
  var tbody = document.getElementById("tableBody");
  var rows = tbody.getElementsByTagName("tr");
  var visibleCount = 0;
  var totalCount = 0;
  var hideOffline = document.getElementById("hideOfflineCheckbox").checked;
  
  for (var i = 0; i < rows.length; i++) {
    var isOffline = rows[i].getAttribute("data-offline") === "true";
    var isHiddenBySearch = rows[i].classList.contains("hidden");
    var isHiddenByOffline = hideOffline && isOffline;
    
    if (!isHiddenByOffline) {
      totalCount++;
      if (!isHiddenBySearch) {
        visibleCount++;
      }
    }
  }
  
  var resultsSpan = document.getElementById("searchResults");
  if (filter === "") {
    resultsSpan.textContent = "Showing " + totalCount + " access points";
  } else {
    resultsSpan.textContent = "Showing " + visibleCount + " of " + totalCount + " access points";
  }
}

function clearSearch() {
  var input = document.getElementById("searchInput");
  input.value = "";
  searchTable();
  input.focus();
}
</script>

</body>
</html>
''')

    return ''.join(html_parts)

class CustomHTTPRequestHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/version'):
            # Return the current version
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
            self.end_headers()
            self.wfile.write(current_page_version["version"].encode())
        elif self.path == '/' or self.path == '/index.html':
            # Serve the HTML file
            self.path = '/meraki-ap-util.html'
            return SimpleHTTPRequestHandler.do_GET(self)
        else:
            return SimpleHTTPRequestHandler.do_GET(self)
    
    def log_message(self, format, *args):
        # Suppress log messages
        pass

def run_web_server(port=8080):
    server_address = ('', port)
    httpd = HTTPServer(server_address, CustomHTTPRequestHandler)
    print(f"\n🌐 Web server started at http://localhost:{port}")
    httpd.serve_forever()

def main():
    # Check if org.txt exists and is not empty
    org_id = read_file("org.txt")
    if org_id is None:
        print("❌ Please create org.txt file in the same folder as Python script and save your Organization ID to the file.")
        sys.exit(1)
    
    # Check if token.txt exists and is not empty
    api_key = read_file("token.txt")
    if api_key is None:
        print("❌ Please create token.txt file in the same folder as Python script and save your API token to the file.")
        sys.exit(1)

    try:
        networks = get_networks(org_id, api_key)
    except requests.HTTPError as e:
        print(f"HTTP error occurred while fetching networks: {e}")
        return
    except Exception as e:
        print(f"An error occurred while fetching networks: {e}")
        return

    if not networks:
        print("No networks found in the organization.")
        return

    print("Available Networks:\n")
    network_name_to_id = {}
    for idx, network in enumerate(networks, start=1):
        name = network.get("name", "Unknown Network Name")
        network_id = network.get("id")
        network_name_to_id[name] = network_id
        print(f"{idx}. {name}")

    selected_network_name = input("\nEnter the exact network name from the list above: ").strip()

    if selected_network_name not in network_name_to_id:
        print("Entered network name not found in the list. Exiting.")
        return

    selected_network_id = network_name_to_id[selected_network_name]

    try:
        device_names_map = get_device_names(org_id, api_key, selected_network_id)
        device_models_map = get_device_models(org_id, api_key, selected_network_id)
    except requests.HTTPError as e:
        print(f"HTTP error occurred while fetching device info: {e}")
        return
    except Exception as e:
        print(f"An error occurred while fetching device info: {e}")
        return

    # Start web server in a separate thread
    web_server_thread = threading.Thread(target=run_web_server, args=(8080,), daemon=True)
    web_server_thread.start()
    
    time.sleep(1)  # Give the server a moment to start

    print("\nStarting continuous monitoring. Press Ctrl+C to stop.\n")
    
    iteration = 0
    browser_opened = False
    
    while True:
        try:
            iteration += 1
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{current_time}] Update #{iteration} - Fetching data...")
            
            # Get all wireless device statuses (online and offline)
            try:
                print(f"Checking wireless access points status...")
                online_wireless_serials, offline_wireless_devices = get_all_wireless_devices(org_id, api_key, selected_network_id, device_names_map)
                print(f"\nTotal online wireless access points: {len(online_wireless_serials)}")
                print(f"Total offline wireless access points: {len(offline_wireless_devices)}")
            except requests.HTTPError as e:
                print(f"HTTP error occurred while fetching device statuses: {e}")
                time.sleep(60)
                continue
            except Exception as e:
                print(f"An error occurred while fetching device statuses: {e}")
                time.sleep(60)
                continue
            
            # Convert to list for processing
            online_serials = list(online_wireless_serials)
            
            # Only fetch data for online devices
            if online_serials:
                print(f"Fetching wireless connection stats for per-band client counts...")
                try:
                    connection_stats_map = get_wireless_connection_stats(api_key, selected_network_id, online_serials)
                except Exception as e:
                    print(f"An error occurred while fetching connection stats: {e}")
                    time.sleep(60)
                    continue

                print(f"Fetching channel utilization per band...")
                try:
                    utilization_per_band_map = get_channel_utilization_per_band(api_key, selected_network_id, online_serials)
                except Exception as e:
                    print(f"An error occurred while fetching channel utilization per band: {e}")
                    time.sleep(60)
                    continue
            else:
                connection_stats_map = {}
                utilization_per_band_map = {}

            html_report = generate_html_report(online_serials, offline_wireless_devices, device_names_map, device_models_map, 
                                               selected_network_name, connection_stats_map, 
                                               utilization_per_band_map, current_time)

            with open("meraki-ap-util.html", "w", encoding="utf-8") as f:
                f.write(html_report)

            print(f"Report updated successfully at {current_time}")
            
            # Open browser after first HTML generation
            if not browser_opened:
                print(f"\n🖥️  Opening http://localhost:8080 in your default browser...")
                webbrowser.open('http://localhost:8080')
                browser_opened = True
            
            print(f"Waiting 60 seconds before next update...\n")
            
            time.sleep(60)
            
        except KeyboardInterrupt:
            print("\n\nMonitoring stopped by user.")
            print("Final report saved to meraki-ap-util.html")
            break
        except Exception as e:
            print(f"Unexpected error: {e}")
            print("Waiting 60 seconds before retry...\n")
            time.sleep(60)

if __name__ == "__main__":
    main()