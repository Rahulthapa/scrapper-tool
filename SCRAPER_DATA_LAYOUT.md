# Scraper Data Layout - What Gets Extracted

This document shows the complete data structure that the scraper extracts from OpenTable restaurant pages.

## Overview

The scraper extracts data from **individual restaurant pages** on OpenTable. When you provide a listing URL (like a search results page), the scraper:

1. **Extracts all restaurant URLs** from the listing page
2. **Visits each individual restaurant page**
3. **Extracts comprehensive data** from each page

## Data Structure Extracted

### Root Level Fields

```json
{
  "url": "https://www.opentable.com/r/restaurant-name",
  "source": "opentable",
  "name": "Restaurant Name",
  "rating": 4.8,
  "review_count": 4714,
  "price_range": "$31 to $50",
  "cuisine": "Seafood",
  "address": "5350 Westheimer Rd., Houston, TX 77056",
  "neighborhood": "Galleria / Uptown"
}
```

### 1. Overview Section

**Location**: Top of the page, header area

**Fields Extracted**:
- `name` - Restaurant name (h1 tag)
- `rating` - Overall rating (e.g., 4.8)
- `review_count` - Number of reviews (e.g., 4714)
- `price_range` - Price range (e.g., "$31 to $50")
- `cuisine` - Primary cuisine type
- `address` - Full address
- `neighborhood` - Neighborhood/area name

### 2. About Section

**Location**: "About this restaurant" section

**Fields Extracted**:
- `tags` - Array of tags (e.g., ["Good for special occasions", "Fancy", "Good for business meals"])
- `description` - Full restaurant description text

### 3. Details Section

**Location**: "Details" section with all restaurant information

**Fields Extracted** (under `details` object):
- `location` - Address text
- `location_url` - Google Maps link
- `price` - Price range
- `dining_style` - Dining style (e.g., "Casual Elegant")
- `hours` - Hours of operation (multiline text)
- `website` - Restaurant website URL
- `payment_options` - Accepted payment methods (e.g., "AMEX, Diners Club, Discover, Mastercard, Visa")
- `dress_code` - Dress code (e.g., "Business Casual")
- `private_party_facilities` - Description of private party facilities
- `private_party_contact` - Contact for private parties
- `phone` - Phone number
- `cuisines` - Array of cuisine types
- `cross_street` - Cross street information
- `parking_details` - Parking information
- `executive_chef` - Chef name
- `additional` - Array of additional features (e.g., ["Banquet", "Bar/Lounge", "Beer", ...])

### 4. Experiences Section

**Location**: "Experiences" tab/section

**Fields Extracted** (array under `experiences`):
Each experience object contains:
- `title` - Experience name
- `price` - Price per person
- `schedule` - Date range (e.g., "Oct 1, 2025 - May 31, 2026")
- `description` - Full description

### 5. Offers Section

**Location**: "Offers" tab/section

**Fields Extracted** (array under `offers`):
Each offer object contains:
- `title` - Offer name
- `schedule` - Date availability
- `times` - Time availability (e.g., "Sun - Sat - 4:00 PM - 6:00 PM")
- `description` - Full description

### 6. Popular Dishes Section

**Location**: "Popular dishes" section

**Fields Extracted** (array under `popular_dishes`):
Each dish object contains:
- `name` - Dish name
- `description` - Dish description
- `reviews` - Number of reviews (e.g., "25 reviews")
- `image_url` - Photo URL

### 7. Menu Section

**Location**: "Menu" tab/section

**Fields Extracted** (under `menu` object):
- `menu_types` - Array of menu types (e.g., ["Prime Rib Sunday", "DINNER MENU", "Desserts", ...])
- `menu_items` - Array of menu sections, each containing:
  - `section` - Section name (e.g., "Starters", "Entrées")
  - `items` - Array of menu items, each containing:
    - `title` - Item name
    - `price` - Price (if available)
    - `description` - Item description
    - `variations` - Array of size/portion variations with prices
- `last_updated` - Last update date

### 8. Reviews Section

**Location**: "Reviews" tab/section

**Fields Extracted** (under `reviews` object):
- `overall_rating` - Overall rating value
- `rating_breakdown` - Object with category ratings:
  - `Food` - Food rating
  - `Service` - Service rating
  - `Ambience` - Ambience rating
  - `Value` - Value rating
- `noise_level` - Noise level (e.g., "Moderate")
- `summary` - AI-generated summary
- `reviews` - Array of individual reviews, each containing:
  - `reviewer` - Reviewer name
  - `rating` - Rating value
  - `date` - Review date
  - `category_ratings` - Object with category ratings
  - `text` - Review text
  - `restaurant_response` - Restaurant's response (if available)

### 9. FAQs Section

**Location**: "FAQs" section

**Fields Extracted** (array under `faqs`):
Each FAQ object contains:
- `question` - FAQ question
- `answer` - FAQ answer

### 10. Photos Section

**Location**: "Photos" section

**Fields Extracted**:
- `photo_count` - Total number of photos
- `photos` - Array of photo URLs (up to 20)

### 11. Booking Information

**Fields Extracted**:
- `booked_today` - Number of times booked today
- `available_time_slots` - Array of available reservation times

## Logging

All extraction steps are logged to `scraper_logs/scraper_{timestamp}.log` with:
- URLs being visited
- Sections being extracted
- Data found in each section
- Errors encountered
- Processing times

## Example Complete Data Structure

```json
{
  "url": "https://www.opentable.com/r/restaurant-name",
  "source": "opentable",
  "name": "Truluck's - Ocean's Finest Seafood & Crab - Houston",
  "rating": 4.8,
  "review_count": 4714,
  "price_range": "$31 to $50",
  "cuisine": "Seafood",
  "address": "5350 Westheimer Rd., Houston, TX 77056",
  "neighborhood": "Galleria / Uptown",
  "tags": ["Good for special occasions", "Fancy", "Good for business meals"],
  "description": "Truluck's has been Houston's premier destination...",
  "details": {
    "location": "5350 Westheimer Rd., Houston, TX 77056",
    "location_url": "https://www.google.com/maps/...",
    "price": "$31 to $50",
    "dining_style": "Casual Elegant",
    "hours": "Mon–Thu 11:00 am–10:00 pm\nFri 11:00 am–10:30 pm\n...",
    "website": "https://trulucks.com/locations/houston-texas/",
    "payment_options": "AMEX, Diners Club, Discover, Mastercard, Visa",
    "dress_code": "Business Casual",
    "phone": "(713) 783-7270",
    "cuisines": ["Seafood", "Steakhouse"],
    "cross_street": "In between Sage and Yorktown",
    "parking_details": "Public Lot",
    "executive_chef": "Misael Ramirez",
    "additional": ["Banquet", "Bar/Lounge", "Beer", "Cocktails", ...]
  },
  "experiences": [
    {
      "title": "TRU Ninety-Two Prix Fixe Menu – 3 Courses for $59",
      "price": "$59.00 per person",
      "schedule": "Oct 1, 2025 - May 31, 2026",
      "description": "It's never too early to celebrate!..."
    }
  ],
  "offers": [
    {
      "title": "Half Off Happy Hour!",
      "schedule": "Multiple dates available",
      "times": "Sun - Sat - 4:00 PM - 6:00 PM",
      "description": "Join us nightly for an exceptional Happy Hour..."
    }
  ],
  "popular_dishes": [
    {
      "name": "Crab Cake",
      "description": "crisp lettuce tomato tartar sauce toasted buttered bun",
      "reviews": "25 reviews",
      "image_url": "https://images.otstatic.com/..."
    }
  ],
  "menu": {
    "menu_types": ["Prime Rib Sunday", "DINNER MENU", "Desserts", ...],
    "menu_items": [
      {
        "section": "Starters",
        "items": [
          {
            "title": "Little Gem Caesar Salad*",
            "description": "shaved parmesan, parker house croutons...",
            "variations": []
          }
        ]
      }
    ],
    "last_updated": "December 8, 2025"
  },
  "reviews": {
    "overall_rating": 4.8,
    "rating_breakdown": {
      "Food": 4.8,
      "Service": 4.8,
      "Ambience": 4.7,
      "Value": 4.5
    },
    "noise_level": "Moderate",
    "summary": "Truluck's - Ocean's Finest Seafood & Crab in Houston offers...",
    "reviews": [
      {
        "reviewer": "Timothy",
        "rating": 3.0,
        "date": "Dined 1 day ago",
        "category_ratings": {
          "Overall": 3,
          "Food": 5,
          "Service": 5,
          "Ambience": 2
        },
        "text": "The redesign made this restaurant more noisy..."
      }
    ]
  },
  "faqs": [
    {
      "question": "Is this a good pick for date night?",
      "answer": "Yes, Truluck's is a popular choice for date night..."
    }
  ],
  "photos": [
    "https://resizer.otstatic.com/v4/photos/...",
    ...
  ],
  "photo_count": 1090,
  "booked_today": 63,
  "available_time_slots": ["6:15 PM", "6:45 PM", "7:00 PM", ...]
}
```

## Log File Location

Detailed logs are saved to: `scraper_logs/scraper_{YYYYMMDD_HHMMSS}.log`

The log file contains:
- Every URL visited
- Each section extraction attempt
- Data found in each section
- Processing times
- Any errors encountered

