#!/usr/bin/env python3
"""
Gavel Meeting Exporter

This script fetches meeting information from the Alaska Legislature's BASIS API
and provides options to export in various formats including Invintus-compatible CSV.
"""

import requests
import json
import csv
import datetime
import re
import sys
import os
from io import StringIO
from flask import Flask, request, Response, render_template_string

# Configuration
API_BASE_URL = "http://www.akleg.gov/publicservice/basis/"
API_VERSION = "1.4"

# Encoder options
ENCODERS = [
    {"name": "> SRT-KTOOENC01", "id": "hm4mevet"},
    {"name": "> SRT-KTOOENC02", "id": "w7tvhokr"},
    {"name": "> SRT-KTOOENC03", "id": "q2ebqzmb"},
    {"name": "> SRT-KTOOENC04", "id": "fo2axzyw"},
    {"name": "> SRT-KTOOENC05", "id": "uzmbsgc4"},
    {"name": "AK Leg Stream 1", "id": "rnbkqv4t"},
    {"name": "AK Leg Stream 2", "id": "d4ayhbnx"},
    {"name": "AK Leg Stream 3", "id": "l7kmwzbd"},
    {"name": "AK Leg Stream 4", "id": "zrld0xmf"},
    {"name": "AK Leg Stream 5", "id": "yxlm1fas"},
    {"name": "AK Leg Stream 6", "id": "hcrujfx7"}
]

# Flask app setup
app = Flask(__name__)

def get_meetings(date):
    """Gets meetings for a specific date"""
    # Create headers for the request
    headers = {
        "X-Alaska-Legislature-Basis-Version": API_VERSION,
        "X-Alaska-Legislature-Basis-Query": f"meetings;date={date};details",
        "Accept-language": "en"
    }
    
    # Get the meetings data
    url = f"{API_BASE_URL}meetings?json=true"
    
    try:
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            return {"error": f"Failed to retrieve meetings data. Status code: {response.status_code}"}
        
        # Decode JSON response
        meetings_data = response.json()

        # Check structure
        if not meetings_data:
            return {"error": "Empty response"}

        if "Basis" not in meetings_data:
            return {"error": "No 'Basis' field in response"}

        if "Meetings" not in meetings_data["Basis"]:
            return {"error": "No 'Meetings' field in Basis"}

        # Get the meetings list
        meetings = meetings_data["Basis"]["Meetings"]
        
        # Make sure we have a list even if there's a different structure
        if not isinstance(meetings, list):
            if isinstance(meetings, dict) and "Meeting" in meetings:
                meetings = meetings["Meeting"]
                if not isinstance(meetings, list):
                    meetings = [meetings]
            else:
                return {"error": "Unexpected structure in Meetings field"}
        
        return meetings
       
    except Exception as e:
        import traceback
        return {"error": f"Exception: {str(e)}"}

def get_meeting_range(start_date, end_date):
    """Get meetings for a date range"""
    # Parse dates
    try:
        start = datetime.datetime.strptime(start_date, "%m/%d/%Y")
        end = datetime.datetime.strptime(end_date, "%m/%d/%Y")
    except ValueError:
        return {"error": "Invalid date format. Please use MM/DD/YYYY."}
    
    # Check range
    if (end - start).days > 30:
        return {"error": "Date range too large. Maximum range is 30 days."}
    
    meetings_by_date = {}
    
    # Get meetings for each date in the range
    current = start
    while current <= end:
        date_str = current.strftime("%m/%d/%Y")
        meetings = get_meetings(date_str)
        meetings_by_date[date_str] = meetings
        current += datetime.timedelta(days=1)
    
    return meetings_by_date

def get_chamber(meeting):
    """Get chamber name from meeting data"""
    chamber = meeting.get("Chamber")
    if chamber == "S":
        return "Senate"
    elif chamber == "H":
        return "House"
    return None

def build_title(meeting):
    """Build a formatted title for the meeting"""
    title = meeting.get("MeetingTitle", "")
    if not title:
        return ""
    
    chamber = get_chamber(meeting)
    committee = title.title()  # Convert to title case
    
    sponsor_type = meeting.get("SponsorType")
    
    if sponsor_type == "Standing Committee" and chamber:
        return f"{chamber} {committee} Committee"
    elif sponsor_type == "Special Committee" and chamber:
        return f"{chamber} {committee} Special Committee"
    elif sponsor_type == "Finance SubCommittee" and chamber:
        return f"{chamber} Finance: {committee} Subcommittee"
    
    return title.title()
    
def format_short_date(date_str):
    """Format date string to 'MM/DD/YY'"""
    try:
        # Parse the date (assuming MM/DD/YYYY format)
        date_obj = datetime.datetime.strptime(date_str, "%m/%d/%Y")
        # Format with shorter year
        return date_obj.strftime("%m/%d/%y")
    except ValueError:
        # Return original if there's an issue
        return date_str
    
def format_date_with_day(date_str):
    """Format date string with day of week: 'Tuesday April 22, 2025'"""
    try:
        # Parse the date (assuming MM/DD/YYYY format)
        date_obj = datetime.datetime.strptime(date_str, "%m/%d/%Y")
        # Format with day of week
        return date_obj.strftime("%A %B %d, %Y")
    except ValueError:
        # Return original if there's an issue
        return date_str

def extract_bills_with_details(meeting):
    """Extract bills with their related details from meeting slices"""
    bill_details = []
    meeting_slices = meeting.get("MeetingSlices", [])
    
    # Group slices by bill
    current_bill = None
    current_details = []
    
    # Track what details we've already added to avoid duplicates
    used_details = set()
    
    for slice in meeting_slices:
        bill_root = slice.get("BillRoot", "")
        highlight_text = slice.get("SliceHighliteText", "")
        
        # Skip empty slices
        if not bill_root and not highlight_text:
            continue
            
        # If we have a new bill, start a new group
        if bill_root and bill_root != current_bill:
            # Save the previous bill group if it exists
            if current_bill and current_details:
                bill_details.append({"bill": current_bill, "details": current_details})
                
            # Start a new group
            current_bill = bill_root
            current_details = []
        
        # Add highlight text as a detail for the current bill
        if current_bill and highlight_text and "MEETING CANCELED" not in highlight_text.upper():
            # Don't add the bill itself as a detail
            if not (bill_root and bill_root == highlight_text):
                # Remember we've used this detail with a bill
                used_details.add(highlight_text)
                current_details.append(highlight_text)
    
    # Add the last bill group if it exists
    if current_bill and current_details:
        bill_details.append({"bill": current_bill, "details": current_details})
    
    # Find slices with no bill but with highlight text that hasn't been used with a bill
    general_items = []
    for slice in meeting_slices:
        bill_root = slice.get("BillRoot", "")
        highlight_text = slice.get("SliceHighliteText", "")
        
        if not bill_root and highlight_text and "MEETING CANCELED" not in highlight_text.upper():
            # Only add items that weren't already associated with a bill
            if highlight_text not in used_details and highlight_text not in general_items:
                general_items.append(highlight_text)
    
    return bill_details, general_items

def build_description(meeting, for_csv=False):
    """Build a description from the meeting slices and bills with their details
    
    Args:
        meeting: The meeting data
        for_csv: If True, excludes stream info from the description
    """
    description_parts = []
    
    # Check if meeting is canceled
    if meeting.get("MeetingCanceled", False):
        description_parts.append("** MEETING CANCELED **")
    
    # Get bills with their details
    bill_details, general_items = extract_bills_with_details(meeting)
    
    # Format bills with their details
    if bill_details:
        bill_texts = []
        for item in bill_details:
            bill = item["bill"]
            details = item["details"]
            
            if details:
                # Get the short title for the bill if available
                short_title = ""
                for slice in meeting.get("MeetingSlices", []):
                    if slice.get("BillRoot") == bill and "ShortTitle" in slice:
                        short_title = slice.get("ShortTitle", "")
                        break
                
                # Use short title if available, otherwise just use bill number
                if short_title:
                    bill_text = f"{bill} {short_title}"
                else:
                    bill_text = bill
                
                # Add details after the bill
                bill_text += " " + " ".join(details)
            else:
                bill_text = bill
                
            bill_texts.append(bill_text)
        
        description_parts.append("Bills: " + ", ".join(bill_texts))
    
    # Add general items
    if general_items:
        description_parts.append(" | ".join(general_items))
    
    # Build the full description
    description = " | ".join(description_parts)
    
    # Remove streaming info for CSV exports if needed
    if for_csv:
        description = description.replace("**Streamed live on AKL.tv**", "").replace(" |  | ", " | ").strip()
        # Clean up any trailing or double separators after removing streaming info
        while " | |" in description:
            description = description.replace(" | |", " |")
        if description.endswith(" | "):
            description = description[:-3]
    
    return description

def should_skip_event(meeting):
    """Determine if a meeting should be skipped"""
    # Skip "No meeting scheduled" meetings
    meeting_slices = meeting.get("MeetingSlices", [])
    for slice in meeting_slices:
        highlight_text = slice.get("SliceHighliteText", "").strip().lower()
        if highlight_text == "no meeting scheduled":
            return True
    
    return False

def generate_custom_id(meeting):
    """Generate a custom ID for the meeting"""
    date_str = meeting.get("MeetingDate", "")
    time_str = meeting.get("MeetingTime", "")
    
    if not date_str or not time_str:
        return "unknown"
    
    chamber = meeting.get("Chamber", "")
    sponsor = meeting.get("MeetingSponsor", "")
    return f"{chamber}-{sponsor}{date_str.replace('-', '')}{time_str.replace(':', '')}"

def render_index_html():
    """Render index page HTML"""
    today = datetime.datetime.now().strftime("%m/%d/%Y")
    tomorrow = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime("%m/%d/%Y")
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Gavel Meeting Exporter</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            h1, h2 {{ color: #003366; }}
            h3 {{ margin-top: 30px; }}
            .tab {{ overflow: hidden; border: 1px solid #ccc; background-color: #003366; }}
            .tab button {{ background-color: #003366; color: white; float: left; border: none; outline: none; cursor: pointer; padding: 14px 16px; font-weight: bold; }}
            .tab button:hover {{ background-color: #005599; }}
            .tab button.active {{ background-color: #005599; }}
            .tabcontent {{ display: none; padding: 20px; border: 1px solid #ccc; border-top: none; }}
            .form-row {{ margin-bottom: 15px; }}
            label {{ display: block; margin-bottom: 5px; }}
            input[type="text"] {{ padding: 5px; width: 200px; }}
            button {{ padding: 8px 15px; background-color: #003366; color: white; border: none; cursor: pointer; }}
            .date-picker {{ position: relative; }}
            .date-picker input {{ padding-right: 30px; }}
            .date-picker:after {{ content: "📅"; position: absolute; right: 5px; top: 7px; pointer-events: none; }}
        </style>
        <link rel="stylesheet" href="https://code.jquery.com/ui/1.12.1/themes/base/jquery-ui.css">
        <script src="https://code.jquery.com/jquery-1.12.4.js"></script>
        <script src="https://code.jquery.com/ui/1.12.1/jquery-ui.js"></script>
        <script>
            $(function() {{
                $(".datepicker").datepicker({{
                    dateFormat: "mm/dd/yy",
                    changeMonth: true,
                    changeYear: true
                }});
            }});
        </script>
    </head>
    <body>
        <h1>Gavel Meeting Exporter</h1>
        
        <div class="tab">
            <button id="single-btn" class="tablinks active" onclick="openTab('single')">Single Date</button>
            <button id="range-btn" class="tablinks" onclick="openTab('range')">Date Range</button>
        </div>
        
        <div id="single" class="tabcontent" style="display: block;">
            <h3>View Meetings for a Single Date</h3>
            <form action="/view" method="get">
                <div class="form-row date-picker">
                    <label for="date">Date (MM/DD/YYYY):</label>
                    <input type="text" id="date" name="date" value="{today}" class="datepicker" required>
                </div>
                <button type="submit">View Meetings</button>
            </form>
        </div>
        
        <div id="range" class="tabcontent">
            <h3>View Meetings for a Date Range</h3>
            <form action="/view_range" method="get">
                <div class="form-row date-picker">
                    <label for="start_date">Start Date (MM/DD/YYYY):</label>
                    <input type="text" id="start_date" name="start_date" value="{today}" class="datepicker" required>
                </div>
                <div class="form-row date-picker">
                    <label for="end_date">End Date (MM/DD/YYYY):</label>
                    <input type="text" id="end_date" name="end_date" value="{tomorrow}" class="datepicker" required>
                </div>
                <button type="submit">View Date Range</button>
            </form>
        </div>
        
        <script>
            function openTab(tabName) {{
                var i, tabcontent, tablinks;
                tabcontent = document.getElementsByClassName("tabcontent");
                for (i = 0; i < tabcontent.length; i++) {{
                    tabcontent[i].style.display = "none";
                }}
                tablinks = document.getElementsByClassName("tablinks");
                for (i = 0; i < tablinks.length; i++) {{
                    tablinks[i].className = tablinks[i].className.replace(" active", "");
                }}
                document.getElementById(tabName).style.display = "block";
                document.getElementById(tabName + "-btn").className += " active";
            }}
        </script>
    </body>
    </html>
    """
    
    return html

def render_meetings_html(meetings, date_info, is_range=False):
    """Render meetings list HTML"""
    if isinstance(meetings, dict) and "error" in meetings:
        return f"<h1>Error</h1><p>{meetings['error']}</p>"
    
    if is_range:
        start_formatted = format_date_with_day(date_info['start'])
        end_formatted = format_date_with_day(date_info['end'])
        title = f"Gavel Meeting Exporter - {start_formatted} to {end_formatted}"
    else:
        formatted_date = format_date_with_day(date_info)
        title = f"Gavel Meeting Exporter - {formatted_date}"    
        
    # Prepare meetings by date for display
    meetings_by_date = {}
    if is_range:
        # For range view, we already have the meetings organized by date
        for date, date_meetings in meetings.items():
            if isinstance(date_meetings, list):
                # Filter out meetings that should be skipped
                valid_meetings = [m for m in date_meetings if not should_skip_event(m)]
                if valid_meetings:  # Only add dates with valid meetings
                    meetings_by_date[date] = valid_meetings
                    # Add date info to each meeting
                    for meeting in valid_meetings:
                        meeting['_display_date'] = date
    else:
        # For single date view, organize under the one date
        valid_meetings = [m for m in meetings if not should_skip_event(m)]
        if valid_meetings:
            meetings_by_date[date_info] = valid_meetings
    
    # Count total valid meetings
    total_meetings = sum(len(meetings) for meetings in meetings_by_date.values())
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{title}</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            h1, h2, h3 {{ color: #003366; }}
            table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
            th, td {{ padding: 8px; text-align: left; border: 1px solid #ddd; vertical-align: top; }}
            th {{ background-color: #003366; color: white; }}
            tr:nth-child(even) {{ background-color: #f2f2f2; }}
            .canceled {{ color: #cc0000; font-weight: bold; }}
            .btn {{ padding: 8px 15px; background-color: #003366; color: white; border: none; cursor: pointer; margin-right: 10px; margin-bottom: 10px; }}
            form {{ margin-top: 20px; }}
            label {{ display: block; margin: 8px 0; }}
            input[type="text"] {{ padding: 5px; width: 200px; }}
            input[type="checkbox"] {{ margin-right: 5px; }}
            .export-form {{ background-color: #f9f9f9; padding: 15px; border: 1px solid #ddd; border-radius: 4px; margin-top: 20px; }}
            .form-row {{ margin-bottom: 10px; }}
            .checkbox-row {{ margin-bottom: 5px; }}
            .back-btn {{ margin-bottom: 20px; }}
            .date-header {{ background-color: #003366; color: white; padding: 10px; margin-top: 30px; margin-bottom: 0; }}
            .description-cell {{ max-width: 300px; white-space: normal; }}
            .encoder-select {{ display: none; width: 200px; }}
            .encoder-select.active {{ display: block; }}
            select {{ padding: 5px; }}
        </style>
    </head>
    <body>
        <a href="/" class="btn back-btn">← Back to Date Selection</a>
        
        <h1>{title}</h1>
        
        <div class="export-options">
            <a href="{'export_csv_range' if is_range else 'export_csv'}?date={date_info['start'] if is_range else date_info}" class="btn">Export All to CSV</a>
        </div>
        
        <h2>Meetings</h2>
    """
    
    if not total_meetings:
        html += "<p>No meetings found for this date period.</p>"
        html += "</body></html>"
        return html
    
    html += f"<p>Found {total_meetings} meetings. Select meetings for Invintus export:</p>"
    
    # Start form for Invintus export
    html += f"""
    <form method="post" action="{'export_invintus_range' if is_range else 'export_invintus'}" id="invintus-form">
        <input type="hidden" name="date_info" value="{date_info['start'] + ' to ' + date_info['end'] if is_range else date_info}">
        
        <div>
            <button type="button" class="btn" onclick="selectAll()">Select All</button>
            <button type="button" class="btn" onclick="deselectAll()">Deselect All</button>
        </div>
    """
    
    # For each date, create a table
    for date in sorted(meetings_by_date.keys()):
        date_meetings = meetings_by_date[date]
    
        # Add date header - CHANGE THIS LINE
        formatted_date = format_date_with_day(date)
        html += f'<h3 class="date-header">Meetings for {formatted_date}</h3>'
    
        # Add table for this date
        html += """
        <table>
            <tr>
                <th>Select</th>
                <th>Date</th>
                <th>Title</th>
                <th>Status</th>
                <th>Location</th>
                <th>Time</th>
                <th>Encoder</th>
                <th>Bills</th>
                <th>Description</th>
            </tr>
        """
        
        # Add meeting rows for this date
        for i, meeting in enumerate(date_meetings):
            # Get basic meeting info
            title = build_title(meeting)
            location = meeting.get("Location", "No Location")
            canceled = meeting.get("MeetingCanceled", False)
            status = '<span class="canceled">CANCELED</span>' if canceled else "Active"
            
            # Format time
            time_str = meeting.get("MeetingTime", "")
            if time_str:
                try:
                    time_obj = datetime.datetime.strptime(time_str, "%H:%M:%S")
                    formatted_time = time_obj.strftime("%I:%M %p")
                except ValueError:
                    formatted_time = time_str
            else:
                formatted_time = "No Time"
            
            # Get bills with details
            bill_details, _ = extract_bills_with_details(meeting)
            bills_str = ", ".join([item["bill"] for item in bill_details]) if bill_details else "None"
            
            # Get description (keep streaming info for HTML display)
            description = build_description(meeting)
            
            # Generate custom ID for this meeting
            custom_id = generate_custom_id(meeting)
            meeting_row_id = f"meeting-{date.replace('/', '')}-{i}"
            
            # Add row to table
            html += f"<tr id='{meeting_row_id}'>"
            
            # Select checkbox
            html += f"""
            <td>
                <input type="checkbox" name="selected_meetings" value="{custom_id}" 
                    data-meeting-id="{meeting_row_id}" 
                    data-title="{title}" 
                    onchange="toggleEncoder(this)">
            </td>
            """

            # Date column - this is new
            html += f"<td>{format_short_date(date)}</td>"

            # Other columns
            html += f"<td>{title}</td>"
            html += f"<td>{status}</td>"
            html += f"<td>{location}</td>"
            html += f"<td>{formatted_time}</td>"
            
            # Encoder dropdown
            html += f"""
            <td>
                <select name="encoder_{custom_id}" class="encoder-select" id="encoder-{meeting_row_id}">
                    <option value="">Select Encoder</option>
            """
            
            # Add encoder options
            for encoder in ENCODERS:
                html += f'<option value="{encoder["id"]}">{encoder["name"]}</option>'
            
            html += """
                </select>
            </td>
            """
            
            # Bills and Description
            html += f"<td>{bills_str}</td>"
            html += f'<td class="description-cell">{description}</td>'
            
            html += "</tr>"
        
        html += "</table>"
    
    # Add Invintus export options
    html += """
    <div class="export-form">
        <h3>Invintus Export Options</h3>
        
        <div class="form-row">
            <label for="runtime">Estimated Runtime (HH:MM):</label>
            <input type="text" id="runtime" name="runtime" value="01:00" pattern="[0-9]{2}:[0-9]{2}" title="Format: HH:MM (e.g., 01:30)" required>
        </div>
        
        <div class="form-row checkbox-row">
            <label>
                <input type="checkbox" id="live_to_break" name="live_to_break" value="TRUE" checked>
                Live To Break
            </label>
        </div>
        
        <div class="form-row">
            <button type="submit" class="btn">Export Selected to Invintus CSV</button>
        </div>
    </div>
    </form>
    
    // Replace the entire script section in your render_meetings_html function with this:

    <script>
function selectAll() {
    var checkboxes = document.querySelectorAll('input[name="selected_meetings"]');
    checkboxes.forEach(function(checkbox) {
        checkbox.checked = true;
        toggleEncoder(checkbox);
    });
}

function deselectAll() {
    var checkboxes = document.querySelectorAll('input[name="selected_meetings"]');
    checkboxes.forEach(function(checkbox) {
        checkbox.checked = false;
        toggleEncoder(checkbox);
    });
}

function toggleEncoder(checkbox) {
    var meetingId = checkbox.getAttribute('data-meeting-id');
    var encoderSelect = document.getElementById('encoder-' + meetingId);
    
    if (checkbox.checked) {
        encoderSelect.classList.add('active');
        
        // Set default category as "Gavel Alaska, [Title]"
        var title = checkbox.getAttribute('data-title');
        var meetingValue = checkbox.value;
        var hiddenInput = document.getElementById('category-' + meetingValue);
        
        if (!hiddenInput) {
            hiddenInput = document.createElement('input');
            hiddenInput.type = 'hidden';
            hiddenInput.name = 'category_' + meetingValue;
            hiddenInput.id = 'category-' + meetingValue;
            document.getElementById('invintus-form').appendChild(hiddenInput);
        }
        
        hiddenInput.value = 'Gavel Alaska, ' + title;
    } else {
        encoderSelect.classList.remove('active');
        encoderSelect.value = '';
        
        // Remove category hidden input
        var meetingValue = checkbox.value;
        var hiddenInput = document.getElementById('category-' + meetingValue);
        if (hiddenInput) {
            hiddenInput.parentNode.removeChild(hiddenInput);
        }
    }
}

document.getElementById('invintus-form').onsubmit = function(e) {
    var checkboxes = document.querySelectorAll('input[name="selected_meetings"]:checked');
    if (checkboxes.length === 0) {
        alert('Please select at least one meeting to export.');
        e.preventDefault();
        return false;
    }
    
    // Check if any selected meetings don't have encoders
    var missingEncoders = false;
    var encoderSelects = [];
    
    checkboxes.forEach(function(checkbox) {
        var meetingId = checkbox.getAttribute('data-meeting-id');
        var encoderSelect = document.getElementById('encoder-' + meetingId);
        
        if (!encoderSelect.value) {
            missingEncoders = true;
            encoderSelects.push(encoderSelect);
        }
    });
    
    // If some encoders are missing, show a warning but allow continuing
    if (missingEncoders) {
        // Highlight the missing encoders
        encoderSelects.forEach(function(select) {
            select.style.border = '2px solid orange';
        });
        
        // Ask for confirmation
        if (!confirm('Some meetings are missing encoder selections. These will be exported with blank encoder values. Continue?')) {
            e.preventDefault();
            return false;
        }
    }
    
    return true;
};
    </script>
    </body>
    </html>
    """
    
    return html

def format_meetings_csv(meetings, include_date=False):
    """Format meetings for standard CSV"""
    output = StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_ALL)
    
    # Determine fields based on whether we include date
    fields = ['title', 'status', 'location', 'time', 'bills', 'description']
    if include_date:
        fields.insert(0, 'date')
    
    # Write header
    writer.writerow(fields)
    
    # Process each meeting
    for meeting in meetings:
        # Skip meetings that should be excluded
        if should_skip_event(meeting):
            continue
        
        # Get basic meeting info
        title = build_title(meeting)
        location = meeting.get("Location", "No Location")
        canceled = meeting.get("MeetingCanceled", False)
        status = "CANCELED" if canceled else "Active"
        
        # Format time
        time_str = meeting.get("MeetingTime", "")
        date_str = meeting.get("MeetingDate", "")
        formatted_time = ""
        
        if date_str and time_str:
            try:
                dt = datetime.datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
                formatted_time = dt.strftime("%Y-%m-%d %I:%M %p")
            except ValueError:
                formatted_time = f"{date_str} {time_str}"
        
        # Get bills with details for description
        bill_details, _ = extract_bills_with_details(meeting)
        bills_str = ", ".join([item["bill"] for item in bill_details]) if bill_details else ""
        
        # Build description for CSV export (exclude streaming info)
        description = build_description(meeting, for_csv=True)
        
        # Build row
        row = [title, status, location, formatted_time, bills_str, description]
        
        # Add date if needed
        if include_date:
            display_date = meeting.get('_display_date', '')
            row.insert(0, display_date)
        
        # Write row
        writer.writerow(row)
    
    return output.getvalue()

def format_meetings_invintus_csv(meetings, encoders, categories, runtime="01:00", live_to_break=True):
    """Format meetings for Invintus CSV export"""
    output = StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_ALL)
    
    # Write header according to Invintus spec
    writer.writerow(["title", "customID", "startDateTime", "description", "encoder", "category", "location", "estRuntime", "liveToBreak"])
    
def format_meetings_invintus_csv(meetings, encoders, categories, runtime="01:00", live_to_break=True):
    """Format meetings for Invintus CSV export"""
    output = StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_ALL)
    
    # Write header according to Invintus spec
    writer.writerow(["title", "customID", "startDateTime", "description", "encoder", "category", "location", "estRuntime", "liveToBreak"])
    
    # Set default values
    live_to_break_value = "TRUE" if live_to_break else "FALSE"
    
    # Process each meeting
    for meeting in meetings:
        # Skip meetings that should be excluded
        if should_skip_event(meeting):
            continue
        
        # Parse date/time
        date_str = meeting.get("MeetingDate", "")
        time_str = meeting.get("MeetingTime", "")
        
        if not date_str or not time_str:
            continue
        
        try:
            # Format datetime in the required format: YYYY-MM-DD HH:mm:ss
            dt = datetime.datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
            start_datetime = dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        
        # Build meeting data for CSV
        
        # 1. Title
        title = build_title(meeting)
        
        # 2. customID (no whitespace)
        custom_id = generate_custom_id(meeting)
        
        # Include all selected meetings, even if no encoder is set
        if custom_id not in encoders:
            continue  # Skip unselected meetings
        
        # 3. startDateTime already formatted above
        
        # 4. Description - use for_csv=True to exclude streaming info
        description = build_description(meeting, for_csv=True)
        
        # 5. encoder (using selected encoder or empty string if none)
        encoder = encoders[custom_id] if encoders[custom_id] else ""
        
        # 6. category (using custom category for each meeting)
        category = categories.get(custom_id, "Gavel Alaska")
        
        # 7. location
        location = meeting.get("Location", "")
        
        # Write row with all fields
        writer.writerow([
            title,
            custom_id,
            start_datetime,
            description,
            encoder,
            category,
            location,
            runtime,
            live_to_break_value
        ])
    
    return output.getvalue()

# Flask routes
@app.route('/')
def index():
    """Main page with date selection"""
    return render_index_html()

@app.route('/view')
def view_meetings():
    """View meetings for a single date"""
    date = request.args.get('date', datetime.datetime.now().strftime("%m/%d/%Y"))
    
    # Get meetings
    meetings_data = get_meetings(date)
    
    # Render HTML
    return render_meetings_html(meetings_data, date)

@app.route('/view_range')
def view_range():
    """View meetings for a date range"""
    start_date = request.args.get('start_date', datetime.datetime.now().strftime("%m/%d/%Y"))
    end_date = request.args.get('end_date', (datetime.datetime.now() + datetime.timedelta(days=1)).strftime("%m/%d/%Y"))
    
    # Get meetings for the date range
    meetings_by_date = get_meeting_range(start_date, end_date)
    
    # Render HTML
    date_info = {'start': start_date, 'end': end_date}
    return render_meetings_html(meetings_by_date, date_info, True)

@app.route('/export_csv')
def export_csv():
    """Export meetings for a single date as CSV"""
    date = request.args.get('date', datetime.datetime.now().strftime("%m/%d/%Y"))
    
    # Get meetings
    meetings_data = get_meetings(date)
    
    if isinstance(meetings_data, dict) and "error" in meetings_data:
        return f"Error: {meetings_data['error']}"
    
    # Format as CSV
    csv_data = format_meetings_csv(meetings_data)
    
    # Return as downloadable file
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename=meetings_{date.replace('/', '-')}.csv"}
    )

@app.route('/export_csv_range')
def export_csv_range():
    """Export meetings for a date range as CSV"""
    date = request.args.get('date', "")
    
    if " to " in date:
        start_date, end_date = date.split(" to ")
    else:
        start_date = end_date = date
    
    # If we have a single date, use the export_csv endpoint
    if start_date == end_date:
        return export_csv()
    
    # Get meetings for the date range
    meetings_by_date = get_meeting_range(start_date, end_date)
    
    if isinstance(meetings_by_date, dict) and "error" in meetings_by_date:
        return f"Error: {meetings_by_date['error']}"
    
    # Flatten meetings for CSV export
    all_meetings = []
    for date, meetings in meetings_by_date.items():
        if isinstance(meetings, list):
            for meeting in meetings:
                # Add date info to each meeting
                meeting['_display_date'] = date
                all_meetings.append(meeting)
    
    # Format as CSV with date column
    csv_data = format_meetings_csv(all_meetings, True)
    
    # Return as downloadable file
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename=meetings_{start_date.replace('/', '-')}_to_{end_date.replace('/', '-')}.csv"}
    )

@app.route('/export_invintus', methods=['POST'])
def export_invintus():
    """Export selected meetings to Invintus CSV format"""
    date_info = request.form.get('date_info', '')
    selected_meetings = request.form.getlist('selected_meetings')
    runtime = request.form.get('runtime', '01:00')
    live_to_break = 'live_to_break' in request.form
    
    if not selected_meetings:
        return "Error: No meetings selected. Please go back and select at least one meeting."
    
    # Get meetings
    meetings_data = get_meetings(date_info)
    
    if isinstance(meetings_data, dict) and "error" in meetings_data:
        return f"Error: {meetings_data['error']}"
    
    # Get encoders and categories for each meeting
    encoders = {}
    categories = {}
    
    for meeting_id in selected_meetings:
        # Get encoder
        encoder_key = f"encoder_{meeting_id}"
        if encoder_key in request.form and request.form[encoder_key]:
            encoders[meeting_id] = request.form[encoder_key]
        
        # Get category
        category_key = f"category_{meeting_id}"
        if category_key in request.form and request.form[category_key]:
            categories[meeting_id] = request.form[category_key]
    
    # Filter to only selected meetings
    filtered_meetings = []
    
    for meeting in meetings_data:
        custom_id = generate_custom_id(meeting)
        if custom_id in selected_meetings:
            filtered_meetings.append(meeting)
    
    # Generate Invintus CSV
    csv_data = format_meetings_invintus_csv(
        filtered_meetings,
        encoders=encoders,
        categories=categories,
        runtime=runtime,
        live_to_break=live_to_break
    )
    
    # Return as downloadable file
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename=invintus_meetings_{date_info.replace('/', '-')}.csv"}
    )

@app.route('/export_invintus_range', methods=['POST'])
def export_invintus_range():
    """Export selected meetings from a date range to Invintus CSV format"""
    date_info = request.form.get('date_info', '')
    selected_meetings = request.form.getlist('selected_meetings')
    runtime = request.form.get('runtime', '01:00')
    live_to_break = 'live_to_break' in request.form
    
    if not selected_meetings:
        return "Error: No meetings selected. Please go back and select at least one meeting."
    
    # Parse date range
    if " to " in date_info:
        start_date, end_date = date_info.split(" to ")
    else:
        start_date = end_date = date_info
    
    # Get encoders and categories for each meeting
    encoders = {}
    categories = {}
    
    for meeting_id in selected_meetings:
        # Get encoder
        encoder_key = f"encoder_{meeting_id}"
        if encoder_key in request.form and request.form[encoder_key]:
            encoders[meeting_id] = request.form[encoder_key]
        
        # Get category
        category_key = f"category_{meeting_id}"
        if category_key in request.form and request.form[category_key]:
            categories[meeting_id] = request.form[category_key]
    
    # Get meetings
    if start_date == end_date:
        meetings_data = get_meetings(start_date)
        if isinstance(meetings_data, dict) and "error" in meetings_data:
            return f"Error: {meetings_data['error']}"
        all_meetings = meetings_data
    else:
        meetings_by_date = get_meeting_range(start_date, end_date)
        if isinstance(meetings_by_date, dict) and "error" in meetings_by_date:
            return f"Error: {meetings_by_date['error']}"
        
        # Flatten meetings
        all_meetings = []
        for date, meetings in meetings_by_date.items():
            if isinstance(meetings, list):
                all_meetings.extend(meetings)
    
    # Filter to only selected meetings
    filtered_meetings = []
    
    for meeting in all_meetings:
        custom_id = generate_custom_id(meeting)
        if custom_id in selected_meetings:
            filtered_meetings.append(meeting)
    
    # Generate Invintus CSV
    csv_data = format_meetings_invintus_csv(
        filtered_meetings,
        encoders=encoders,
        categories=categories,
        runtime=runtime,
        live_to_break=live_to_break
    )
    
    # Return as downloadable file
    filename = f"invintus_meetings_{start_date.replace('/', '-')}"
    if start_date != end_date:
        filename += f"_to_{end_date.replace('/', '-')}"
    
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={filename}.csv"}
    )

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Gavel Meeting Exporter')
    parser.add_argument('--port', type=int, default=5027,
                        help='Port to run the web server on (default: 5027)')
    
    args = parser.parse_args()
    
    print(f"Starting web server on port {args.port}...")
    print(f"Access the web interface at http://localhost:{args.port}/")
    app.run(host='0.0.0.0', port=args.port)