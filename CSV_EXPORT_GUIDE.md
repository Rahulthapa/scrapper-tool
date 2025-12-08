# CSV Export Guide

## Overview

The CSV export now includes **all extracted URLs** and **all data scraped from each URL** in a flattened, easy-to-read format.

## CSV Structure

### Column Organization

1. **First Column: `url`**
   - Always the first column
   - Contains the restaurant page URL
   - Every row has a URL (even if scraping failed)

2. **Data Columns**
   - All extracted data is flattened into columns
   - Nested structures use underscores (e.g., `details_hours`)
   - Lists are converted to semicolon-separated values

### Example CSV Structure

```csv
url,name,rating,review_count,price_range,cuisine,address,details_hours,details_phone,details_website,reviews_total,menu_sections_count,...
https://www.opentable.com/r/restaurant-1,Restaurant Name,4.5,1234,$$$,Italian,123 Main St,Mon-Fri 11am-10pm,555-1234,https://...,150,5,...
https://www.opentable.com/r/restaurant-2,Another Restaurant,4.2,890,$$,Mexican,456 Oak Ave,Tue-Sun 12pm-11pm,555-5678,https://...,98,3,...
```

## Data Flattening

### Nested Dictionaries
**Before:**
```json
{
  "details": {
    "hours": "Mon-Fri 11am-10pm",
    "phone": "555-1234"
  }
}
```

**After (in CSV):**
```
details_hours,details_phone
Mon-Fri 11am-10pm,555-1234
```

### Lists
**Before:**
```json
{
  "tags": ["Outdoor Seating", "Live Music", "Wheelchair Accessible"]
}
```

**After (in CSV):**
```
tags
Outdoor Seating; Live Music; Wheelchair Accessible
```

### Lists of Objects
**Before:**
```json
{
  "reviews": [
    {"rating": 5, "comment": "Great food"},
    {"rating": 4, "comment": "Good service"}
  ]
}
```

**After (in CSV):**
```
reviews_1_rating,reviews_1_comment,reviews_2_rating,reviews_2_comment
5,Great food,4,Good service
```

## OpenTable Data Structure in CSV

When scraping OpenTable pages, the CSV will include columns for:

### Overview Section
- `url` - Restaurant URL
- `name` - Restaurant name
- `rating` - Star rating
- `review_count` - Number of reviews
- `price_range` - Price range ($$$)
- `cuisine` - Cuisine type
- `address` - Full address
- `neighborhood` - Neighborhood name

### Details Section
- `details_location` - Location description
- `details_hours` - Operating hours
- `details_phone` - Phone number
- `details_website` - Website URL
- `details_dining_style` - Dining style
- `details_payment_options` - Payment methods
- `details_dress_code` - Dress code
- `details_cuisines` - List of cuisines (semicolon-separated)

### Experiences Section
- `experiences_1_title` - First experience title
- `experiences_1_price` - First experience price
- `experiences_1_description` - First experience description
- `experiences_2_title` - Second experience title
- ... (continues for all experiences)

### Menu Section
- `menu_sections_count` - Number of menu sections
- `menu_1_name` - First menu section name
- `menu_1_items_count` - Number of items in first section
- `menu_1_items_1_name` - First item name
- `menu_1_items_1_price` - First item price
- ... (continues for all menu items)

### Reviews Section
- `reviews_total` - Total number of reviews
- `reviews_overall_rating` - Overall rating
- `reviews_noise_level` - Noise level
- `reviews_1_rating` - First review rating
- `reviews_1_comment` - First review comment
- ... (continues for all reviews)

### Other Sections
- `tags` - All tags (semicolon-separated)
- `description` - Restaurant description
- `photos_count` - Number of photos
- `faqs_count` - Number of FAQs

## Complete URL Coverage

### All URLs Included
- ✅ **All extracted URLs** are included in the CSV
- ✅ **Even failed scrapes** are included (with `scraping_status: failed`)
- ✅ **Source listing URL** is included in `source_listing_url` column

### Failed Scrapes
If a URL couldn't be scraped, the row will have:
- `url` - The URL that was attempted
- `scraping_status` - "failed"
- `error` - Error message (if available)
- Other fields will be empty

## Example: Complete CSV Row

```csv
url,name,rating,review_count,price_range,cuisine,address,details_hours,details_phone,details_website,tags,description,reviews_total,menu_sections_count,source_listing_url
https://www.opentable.com/r/steak-48-houston,Steak 48,4.6,2341,$$$$,Steakhouse,4444 Westheimer Rd,Mon-Thu 5pm-10pm; Fri-Sat 5pm-11pm; Sun 5pm-9pm,(713) 622-4848,https://steak48.com,Outdoor Seating; Private Dining; Wheelchair Accessible,Modern American steakhouse...,2341,8,https://www.opentable.com/metro/houston-restaurants
```

## Benefits

1. **Complete Data**: All extracted URLs and their data in one file
2. **Easy Analysis**: Flattened structure works with Excel, Google Sheets, etc.
3. **No Data Loss**: Even failed scrapes are included
4. **Traceable**: Source listing URL included for each row
5. **Structured**: Consistent column naming makes it easy to parse

## Usage

### Export CSV
```bash
GET /jobs/{job_id}/export?format=csv
```

### Download CSV
The CSV file will include:
- All 109 extracted URLs (or however many were found)
- All data scraped from each URL
- Flattened structure for easy analysis
- Source listing URL for traceability

## Tips

1. **Open in Excel/Google Sheets** for better viewing
2. **Filter by `scraping_status`** to see which URLs failed
3. **Sort by `rating`** to find top-rated restaurants
4. **Use `source_listing_url`** to group by listing page
5. **Search for specific columns** like `cuisine` or `price_range`

