# Gavel Meeting Exporter

A tool for retrieving, displaying, and exporting Alaska Legislature meeting information from the BASIS API. Designed specifically for preparing meeting data for broadcast systems like Invintus.

## Overview

Gavel Meeting Exporter is a Flask-based web application that allows users to:

1. Fetch meeting data from the Alaska Legislature's BASIS API
2. View meetings by date or date range
3. Export meeting data to standard CSV format
4. Select specific meetings and export them in Invintus-compatible CSV format for broadcast scheduling

This tool streamlines the workflow for broadcasting legislative meetings by providing a user-friendly interface to access meeting data and prepare it for automation systems.

## Features

- **Meeting Retrieval**: Fetch meeting information for specific dates or date ranges
- **Interactive Interface**: Select meetings, assign encoders, and set runtime parameters
- **Bill Information**: Display bills being discussed in each meeting
- **Meeting Details**: Show location, time, status, and descriptions
- **Export Options**:
  - Standard CSV export with all meetings
  - Invintus-compatible CSV with selected meetings and encoder assignments
- **Encoder Assignment**: Select encoders for each meeting

## Requirements

- Python 3.6+
- Flask
- Requests
- Internet connection to access the Alaska Legislature API

## Installation

1. Clone the repository:
   ```
   git clone https://github.com/kburki/gavel-meeting-exporter.git
   cd gavel-meeting-exporter
   ```

2. Create and activate a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```
   pip install flask requests
   ```

## Usage

1. Run the application:
   ```
   python gavel_meeting_tool.py
   ```

2. Access the web interface in your browser:
   ```
   http://localhost:5028
   ```

3. Select a date or date range to view meetings

4. To export all meetings to standard CSV, click the "Export All to CSV" button

5. To export selected meetings to Invintus format:
   - Select meetings by checking the boxes
   - Choose encoders for each selected meeting
   - Set the estimated runtime
   - Click "Export Selected to Invintus CSV"

## API Information

The application uses the Alaska Legislature's BASIS API:
- Base URL: http://www.akleg.gov/publicservice/basis/
- Version: 1.4

## License

his project is licensed under the terms of the MIT license.

## Contributing

Contributions, bug reports, and feature requests are welcome! Feel free to submit issues or pull requests to improve the tool.

## Acknowledgments

- Alaska Legislature for providing the BASIS API
- [KTOO](https://www.ktoo.org/) for supporting development