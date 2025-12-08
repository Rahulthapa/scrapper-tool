# How to Access Scraper Logs

## Overview

The scraper creates detailed logs for every scraping operation. These logs are saved in the `scraper_logs/` directory and can be accessed in multiple ways.

## Log File Location

Logs are automatically saved to:
```
scraper_logs/scraper_YYYYMMDD_HHMMSS.log
```

The directory is created automatically when the scraper runs.

## Access Methods

### 1. **Direct File Access (Local Development)**

If you're running the scraper locally, logs are in:
```
scraper_logs/scraper_YYYYMMDD_HHMMSS.log
```

You can:
- Open the file directly in a text editor
- Use `tail -f scraper_logs/scraper_*.log` to watch logs in real-time
- Use `cat scraper_logs/scraper_*.log` to view all logs

### 2. **API Endpoints (Recommended for Production)**

The scraper provides REST API endpoints to access logs:

#### **List All Log Files**
```bash
GET /logs
```

Returns:
```json
{
  "logs": [
    {
      "filename": "scraper_20251208_143015.log",
      "size": 245678,
      "created": "2025-12-08T14:30:15",
      "modified": "2025-12-08T14:35:22",
      "url": "/logs/scraper_20251208_143015.log"
    }
  ],
  "total": 1,
  "log_directory": "/path/to/scraper_logs"
}
```

#### **Get Latest Log File**
```bash
GET /logs/latest
```

Downloads the most recent log file.

#### **Get Specific Log File**
```bash
GET /logs/{filename}
```

Example:
```bash
GET /logs/scraper_20251208_143015.log
```

Downloads the specified log file.

#### **Get Last N Lines of a Log File**
```bash
GET /logs/{filename}/tail?lines=100
```

Returns the last 100 lines (adjustable, max 1000) as JSON:
```json
{
  "filename": "scraper_20251208_143015.log",
  "total_lines": 5000,
  "returned_lines": 100,
  "lines": [
    "2025-12-08 14:30:15 | INFO | [URL VISIT] STARTED...",
    ...
  ]
}
```

### 3. **Using cURL**

```bash
# List all logs
curl http://localhost:8000/logs

# Get latest log
curl http://localhost:8000/logs/latest -o latest.log

# Get specific log
curl http://localhost:8000/logs/scraper_20251208_143015.log -o logfile.log

# Get last 50 lines
curl "http://localhost:8000/logs/scraper_20251208_143015.log/tail?lines=50"
```

### 4. **Using Python Requests**

```python
import requests

# List all logs
response = requests.get("http://localhost:8000/logs")
logs = response.json()
print(f"Found {logs['total']} log files")

# Get latest log
response = requests.get("http://localhost:8000/logs/latest")
with open("latest.log", "wb") as f:
    f.write(response.content)

# Get last 100 lines
response = requests.get(
    "http://localhost:8000/logs/scraper_20251208_143015.log/tail",
    params={"lines": 100}
)
data = response.json()
for line in data["lines"]:
    print(line)
```

### 5. **In Browser**

Simply navigate to:
- `http://localhost:8000/logs` - List all logs
- `http://localhost:8000/logs/latest` - Download latest log
- `http://localhost:8000/logs/{filename}` - Download specific log

## Production Deployment

### On Render/Heroku/Similar Platforms

1. **Access via API**: Use the API endpoints shown above
2. **SSH Access**: If you have SSH access, logs are in the `scraper_logs/` directory
3. **Download via API**: Use the `/logs/latest` endpoint to download logs

### On Docker

If running in Docker:
```bash
# Copy logs from container
docker cp container_name:/app/scraper_logs ./local_logs

# Or exec into container
docker exec -it container_name bash
cd scraper_logs
cat scraper_*.log
```

## Log File Structure

Each log file contains:
- Timestamp for every entry
- Log level (INFO, WARNING, ERROR, DEBUG)
- Category tags ([URL VISIT], [SECTION], [RESTAURANT], etc.)
- Detailed information about each step

Example log entry:
```
2025-12-08 14:30:17 | INFO | [URL VISIT] STARTED | Method: GET | URL: https://www.opentable.com/r/restaurant-1
2025-12-08 14:30:20 | INFO | [SECTION] STARTED | URL: https://www.opentable.com/r/restaurant-1 | Section: OVERVIEW
2025-12-08 14:30:20 | INFO | [SECTION DATA] URL: https://www.opentable.com/r/restaurant-1 | Section: OVERVIEW | Items Found: 7
```

## Troubleshooting

### Logs Not Appearing?

1. **Check if directory exists**: The `scraper_logs/` directory is created automatically
2. **Check permissions**: Ensure the application has write permissions
3. **Check API**: Use `GET /logs` to see if any logs exist
4. **Check application logs**: The main application logs will show if the logger initialized

### Can't Access Logs in Production?

1. **Use API endpoints**: They work regardless of file system access
2. **Check environment**: Ensure the `scraper_logs/` directory is writable
3. **Use tail endpoint**: The `/logs/{filename}/tail` endpoint is useful for quick checks

## Best Practices

1. **Regular Cleanup**: Log files can grow large. Consider implementing log rotation
2. **Monitor Latest Log**: Use `/logs/latest` to always get the most recent activity
3. **Use Tail for Debugging**: The tail endpoint is perfect for quick debugging without downloading entire files
4. **Archive Old Logs**: Move old logs to archive storage if needed

## Security Note

- Log files may contain URLs and data from scraped pages
- Don't expose logs publicly without proper authentication
- Consider adding authentication to log endpoints in production

