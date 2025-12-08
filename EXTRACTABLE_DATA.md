# Extractable Data - Complete Reference

This document lists all data types that can be extracted using this web scraper tool.

---

## 📊 Data Extraction Capabilities Overview

The scraper can extract data from **any website** using multiple methods:
1. **Static HTML parsing** (BeautifulSoup)
2. **JavaScript-rendered content** (Playwright)
3. **Embedded JSON data** (JSON-LD, Next.js data, site-specific)
4. **Network API responses** (intercepted requests)
5. **JavaScript variables** (window objects, internal state)
6. **AI-powered extraction** (custom prompts with Gemini/OpenAI)

---

## 🍽️ Restaurant/Business Data (Specialized)

### Basic Information
- ✅ Restaurant/Business name
- ✅ Description, tagline, slogan
- ✅ Website URL
- ✅ Social media links (Facebook, Instagram, Twitter, LinkedIn)
- ✅ Business type, establishment type
- ✅ Business category/classification

### Contact Details
- ✅ Phone number (all formats: US, international)
- ✅ Email address
- ✅ Contact form URL
- ✅ Display phone (formatted)

### Location Data
- ✅ Full formatted address
- ✅ Address components:
  - Street address
  - City
  - State/Province
  - ZIP/Postal code
  - Country
- ✅ GPS coordinates (latitude, longitude)
- ✅ Neighborhood/Area name
- ✅ Parking information (valet, street, lot, garage)
- ✅ Public transit access
- ✅ Distance (if from search results)

### Ratings & Reviews
- ✅ Overall rating (numeric)
- ✅ Review count
- ✅ Rating breakdown by category
- ✅ Review sources (Yelp, Google, TripAdvisor, etc.)
- ✅ Best rating, worst rating
- ✅ Review text (if available)

### Pricing & Cost
- ✅ Price range ($, $$, $$$, $$$$)
- ✅ Average cost per person
- ✅ Menu price ranges
- ✅ Happy hour information
- ✅ Special offers, deals, discounts
- ✅ Group pricing

### Cuisine & Menu
- ✅ Cuisine types (all categories)
- ✅ Dietary options:
  - Vegetarian
  - Vegan
  - Gluten-free
  - Halal
  - Kosher
  - Keto-friendly
- ✅ **ALL Menu URLs:**
  - Main menu
  - Lunch menu
  - Dinner menu
  - Brunch menu
  - Drinks menu
  - Dessert menu
  - Online ordering URL
  - Delivery menu URL
  - Takeout menu URL
- ✅ Menu items (if available)
- ✅ Signature dishes
- ✅ Specialties
- ✅ Chef name

### Hours & Availability
- ✅ Opening hours (all days with times)
- ✅ Special hours
- ✅ Happy hour times
- ✅ Brunch hours
- ✅ Closed days
- ✅ Holiday hours

### Amenities & Features
- ✅ Wi-Fi availability
- ✅ Parking (valet, street, lot, garage)
- ✅ Outdoor seating, patio, terrace
- ✅ Indoor seating capacity
- ✅ Private dining rooms
- ✅ Event space
- ✅ Bar area, lounge
- ✅ Live music
- ✅ TV screens
- ✅ Wheelchair accessible
- ✅ High chairs
- ✅ Kid-friendly
- ✅ Pet-friendly
- ✅ Dress code
- ✅ Noise level
- ✅ Ambiance (casual, formal, romantic, family-friendly)
- ✅ Good for groups
- ✅ Good for kids
- ✅ Romantic setting
- ✅ Business meetings
- ✅ Solo dining
- ✅ Date night

### Services & Options
- ✅ Reservations (accepted, required, online booking)
- ✅ Walk-ins
- ✅ Takeout
- ✅ Delivery services:
  - DoorDash
  - Uber Eats
  - Grubhub
  - Postmates
  - Other delivery platforms
- ✅ Curbside pickup
- ✅ Drive-through
- ✅ Catering services
- ✅ Private events
- ✅ Group dining
- ✅ Gift cards

### Payment & Transactions
- ✅ Payment methods:
  - Cash
  - Credit cards
  - Debit cards
  - Mobile payments (Apple Pay, Google Pay)
- ✅ Currencies accepted
- ✅ Tips accepted

### Photos & Media
- ✅ Main image URL
- ✅ Photo gallery URLs
- ✅ Logo URL
- ✅ Menu images
- ✅ Interior photos
- ✅ Exterior photos
- ✅ Food photos
- ✅ All image URLs on page

### Additional Metadata
- ✅ Yelp ID
- ✅ Google Place ID
- ✅ TripAdvisor ID
- ✅ OpenTable ID
- ✅ Business owner information
- ✅ Awards
- ✅ Certifications
- ✅ Years in business
- ✅ Founding date

### Internal Data
- ✅ API response data
- ✅ JavaScript variables (window.__PRELOADED_STATE__, etc.)
- ✅ Internal IDs
- ✅ Analytics data
- ✅ Any other restaurant-related fields

---

## 🌐 General Web Page Data (Any Website)

### Page Structure
- ✅ **Page Title** (from `<title>` or `<h1>`)
- ✅ **URL** (canonical, current)
- ✅ **Page Type** (auto-detected: article, product, blog, form, generic)
- ✅ **Word Count**

### Content
- ✅ **Full Text Content** (all text from page, cleaned)
- ✅ **Main Content** (extracted from `<article>`, `<main>`, or content areas)
- ✅ **Text Content** (body text, limited to 10k chars)

### Links
- ✅ **All Links** (up to 100):
  - Link text
  - Full URL (resolved)
  - Title attribute
  - Context

### Images
- ✅ **All Images** (up to 50):
  - Source URL (full path)
  - Alt text
  - Title attribute
  - Context

### Meta Information
- ✅ **Meta Tags** (all meta tags):
  - Open Graph tags (og:title, og:description, og:image, etc.)
  - Twitter Card tags
  - Standard meta tags (description, keywords, author, etc.)
  - Schema.org microdata

### Headings
- ✅ **All Headings** (H1-H6, up to 20 per level):
  - H1 headings
  - H2 headings
  - H3 headings
  - H4 headings
  - H5 headings
  - H6 headings

### Sections (NEW Feature)
- ✅ **Data Organized by Sections**:
  - Section titles (from H2, H3, H4)
  - Section text content
  - Lists within sections
  - Links within sections
  - Raw content items

### Lists
- ✅ **All Lists** (up to 10):
  - Unordered lists (bullets)
  - Ordered lists (numbered)
  - List items

### Tables
- ✅ **All Tables** (up to 5):
  - Table rows
  - Table cells (headers and data)
  - Structured table data

### Code Blocks
- ✅ **Code Blocks** (up to 10):
  - `<code>` elements
  - `<pre>` elements
  - Code content (limited to 500 chars each)

### Structured Data
- ✅ **JSON-LD Data** (Schema.org):
  - All JSON-LD script tags
  - Structured business data
  - Product information
  - Article metadata
  - Event data
  - Review data
  - And more...

### Embedded Data
- ✅ **Embedded JSON**:
  - JSON-LD structured data
  - Next.js data (`__NEXT_DATA__`)
  - Yelp-specific data patterns
  - Generic JSON in script tags
  - Window variables (__PRELOADED_STATE__, pageData, etc.)

### JavaScript Data (Playwright)
- ✅ **JavaScript Variables**:
  - window.__PRELOADED_STATE__
  - window.__NEXT_DATA__
  - window.pageData
  - window.initialData
  - window.appData
  - Custom site-specific variables

- ✅ **Network Responses**:
  - API call responses (JSON)
  - Search result data
  - Business data from APIs
  - Restaurant listings from APIs

### DOM Data
- ✅ **Rendered DOM Information**:
  - Full HTML content (after JS execution)
  - Page title (after JS)
  - Current URL (after redirects)
  - HTML length

---

## 🔍 Site-Specific Data Extraction

### Yelp
- ✅ Business listings
- ✅ Search results
- ✅ Business details
- ✅ Reviews and ratings
- ✅ Photos
- ✅ Hours
- ✅ Categories
- ✅ Price range
- ✅ Attributes
- ✅ Special hours
- ✅ Distance (from search)

### OpenTable
- ✅ Restaurant listings
- ✅ Availability
- ✅ Reservation information
- ✅ Cuisine types
- ✅ Price ranges
- ✅ Ratings

### Google Maps
- ✅ Place information
- ✅ Business listings
- ✅ Reviews
- ✅ Photos
- ✅ Hours
- ✅ Contact information

### TripAdvisor
- ✅ Business listings
- ✅ Reviews
- ✅ Ratings
- ✅ Photos
- ✅ Location information

---

## 🤖 AI-Powered Custom Extraction

Using AI prompts, you can extract **any custom data** from web pages:

### Examples of Custom Extraction:
- ✅ **Product Data**: Names, prices, descriptions, SKUs, availability
- ✅ **Job Listings**: Title, company, location, salary, requirements
- ✅ **Real Estate**: Address, price, bedrooms, bathrooms, square footage
- ✅ **News Articles**: Headline, author, date, content, tags
- ✅ **Social Media**: Posts, comments, likes, shares, user info
- ✅ **E-commerce**: Products, prices, reviews, stock status
- ✅ **Events**: Name, date, location, description, tickets
- ✅ **People/Profiles**: Name, bio, contact, social links
- ✅ **Financial Data**: Stock prices, market data, financial reports
- ✅ **Academic**: Papers, citations, abstracts, authors
- ✅ **And anything else you can describe in a prompt!**

### Smart Extraction (No AI Required)
The scraper also has built-in pattern matching for:
- ✅ **Email addresses** (regex extraction)
- ✅ **Phone numbers** (multiple formats)
- ✅ **Prices** (various currencies: $, €, £, ₹, etc.)
- ✅ **Business listings** (from headings, images, links)
- ✅ **Ratings** (numeric ratings with review counts)

---

## 📦 Data Export Formats

All extracted data can be exported in:
- ✅ **JSON** (structured format)
- ✅ **CSV** (spreadsheet format)
- ✅ **Excel** (.xlsx format)

---

## 🎯 Extraction Methods

### 1. Static HTML Scraping
- Extracts data from raw HTML
- Fast and efficient
- Works for most static websites

### 2. JavaScript Rendering (Playwright)
- Renders JavaScript-heavy pages
- Extracts fully loaded content
- Captures dynamically loaded data

### 3. Internal Data Extraction
- Extracts from JavaScript variables
- Intercepts network API calls
- Captures internal application state

### 4. Individual Page Extraction
- Visits each restaurant/business page
- Extracts comprehensive details
- Merges listing + detail data

### 5. AI Filtering
- Uses natural language prompts
- Extracts custom data structures
- Handles unstructured content

---

## 📋 Complete Data Structure Example

```json
{
  "url": "https://example.com/restaurant",
  "title": "Restaurant Name",
  "text_content": "Full page text...",
  "main_content": "Main article content...",
  "links": [
    {
      "text": "Link Text",
      "href": "https://example.com/link",
      "title": "Link Title"
    }
  ],
  "images": [
    {
      "src": "https://example.com/image.jpg",
      "alt": "Image description",
      "title": "Image title"
    }
  ],
  "meta_tags": {
    "description": "Page description",
    "og:title": "Open Graph title",
    "og:image": "https://example.com/og-image.jpg"
  },
  "headings": {
    "h1": ["Main Heading"],
    "h2": ["Section 1", "Section 2"],
    "h3": ["Subsection 1.1"]
  },
  "sections": {
    "About Us": {
      "title": "About Us",
      "text": "Section text content...",
      "lists": [["Item 1", "Item 2"]],
      "links": [{"text": "Learn More", "url": "..."}]
    }
  },
  "lists": [
    ["Item 1", "Item 2", "Item 3"]
  ],
  "tables": [
    [
      ["Header 1", "Header 2"],
      ["Data 1", "Data 2"]
    ]
  ],
  "code_blocks": ["code content..."],
  "page_type": "restaurant",
  "structured_data": [
    {
      "@type": "Restaurant",
      "name": "Restaurant Name",
      "address": {...},
      "rating": {...}
    }
  ],
  "restaurants": [
    {
      "name": "Restaurant Name",
      "url": "https://...",
      "phone": "+1-234-567-8900",
      "address": "123 Main St, City, State 12345",
      "address_parts": {
        "street_address": "123 Main St",
        "city": "City",
        "state": "State",
        "postal_code": "12345"
      },
      "rating": 4.5,
      "review_count": 1234,
      "price_range": "$$$",
      "cuisine": ["American", "Steakhouse"],
      "hours": {...},
      "menu_urls": {
        "main_menu": "https://...",
        "lunch_menu": "https://...",
        "dinner_menu": "https://..."
      },
      "amenities": ["Wi-Fi", "Parking", "Outdoor Seating"],
      "services": ["Reservations", "Takeout", "Delivery"],
      "photos": ["https://...", "https://..."],
      "latitude": 40.7128,
      "longitude": -74.0060
    }
  ],
  "embedded_data": {
    "json_ld": [...],
    "next_data": {...},
    "yelp_props": {...}
  },
  "javascript_variables": {
    "__PRELOADED_STATE__": {...},
    "pageData": {...}
  },
  "network_responses": [
    {
      "url": "https://api.example.com/data",
      "status": 200,
      "data": {...}
    }
  ],
  "word_count": 1234,
  "rendered_with_javascript": true
}
```

---

## 🚀 Usage Examples

### Extract Restaurant Data
```python
POST /parse-html
{
  "html": "<html>...</html>",
  "ai_prompt": "Extract all restaurants with complete data"
}
```

### Extract Custom Data
```python
POST /parse-html
{
  "html": "<html>...</html>",
  "ai_prompt": "Extract all product names, prices, and descriptions"
}
```

### Extract from Live URL
```python
POST /extract-internal-data
{
  "url": "https://www.yelp.com/search?find_desc=steakhouse&find_loc=Houston,TX",
  "extract_individual_pages": true
}
```

### Extract from Individual Pages
```python
POST /extract-from-individual-pages
{
  "restaurants": [
    {"name": "Restaurant 1", "url": "https://..."},
    {"name": "Restaurant 2", "url": "https://..."}
  ],
  "use_javascript": true
}
```

---

## 📊 Summary

**Total Data Types Extractable: 100+**

The scraper can extract:
- ✅ **Restaurant/Business data**: 60+ fields
- ✅ **General web page data**: 20+ fields
- ✅ **Structured data**: JSON-LD, Schema.org
- ✅ **JavaScript data**: Variables, API responses
- ✅ **Custom data**: Anything via AI prompts
- ✅ **Site-specific data**: Yelp, OpenTable, Google Maps, etc.

**The scraper is designed to extract EVERY piece of available information from web pages, making it one of the most comprehensive web scraping tools available.**

