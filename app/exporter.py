import pandas as pd
from typing import List, Dict, Any
import json
from io import BytesIO


class DataExporter:
    @staticmethod
    def to_json(data: List[Dict[str, Any]]) -> str:
        """Export data to JSON string"""
        return json.dumps(data, indent=2, default=str)

    @staticmethod
    def _flatten_dict(d: Dict[str, Any], parent_key: str = '', sep: '_') -> Dict[str, Any]:
        """
        Flatten nested dictionary structure for CSV export.
        Example: {'details': {'hours': '9-5'}} -> {'details_hours': '9-5'}
        """
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(DataExporter._flatten_dict(v, new_key, sep=sep).items())
            elif isinstance(v, list):
                # Handle lists: convert to string or expand
                if len(v) > 0 and isinstance(v[0], dict):
                    # List of dicts: create numbered columns
                    for idx, item in enumerate(v):
                        if isinstance(item, dict):
                            items.extend(DataExporter._flatten_dict(item, f"{new_key}_{idx+1}", sep=sep).items())
                        else:
                            items.append((f"{new_key}_{idx+1}", str(item)))
                else:
                    # Simple list: join with semicolon
                    items.append((new_key, '; '.join(str(x) for x in v) if v else ''))
            else:
                items.append((new_key, v))
        return dict(items)

    @staticmethod
    def _prepare_data_for_csv(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Prepare data for CSV export:
        1. Ensure 'url' is always present and first
        2. Flatten nested structures
        3. Handle missing URLs
        """
        flattened_data = []
        
        for item in data:
            if not isinstance(item, dict):
                continue
            
            # Ensure URL is present
            url = item.get('url') or item.get('website') or item.get('yelp_url') or 'N/A'
            
            # Flatten the dictionary
            flattened = DataExporter._flatten_dict(item)
            
            # Ensure URL is the first key
            if 'url' in flattened:
                url_value = flattened.pop('url')
                flattened = {'url': url_value, **flattened}
            else:
                flattened = {'url': url, **flattened}
            
            flattened_data.append(flattened)
        
        return flattened_data

    @staticmethod
    def to_csv(data: List[Dict[str, Any]]) -> bytes:
        """
        Export data to CSV bytes with enhanced formatting:
        - All extracted URLs included
        - Nested data flattened into columns
        - Lists converted to semicolon-separated values
        - URL always in first column
        """
        if not data:
            # Return empty CSV with just headers
            return "url\n".encode('utf-8')
        
        # Prepare data: flatten nested structures
        flattened_data = DataExporter._prepare_data_for_csv(data)
        
        if not flattened_data:
            return "url\n".encode('utf-8')
        
        # Create DataFrame
        df = pd.DataFrame(flattened_data)
        
        # Ensure 'url' is the first column
        if 'url' in df.columns:
            cols = ['url'] + [c for c in df.columns if c != 'url']
            df = df[cols]
        
        # Replace NaN with empty string for cleaner CSV
        df = df.fillna('')
        
        # Convert to CSV
        return df.to_csv(index=False).encode('utf-8')

    @staticmethod
    def to_excel(data: List[Dict[str, Any]]) -> bytes:
        """
        Export data to Excel bytes with enhanced formatting:
        - All extracted URLs included
        - Nested data flattened into columns
        - Lists converted to semicolon-separated values
        """
        if not data:
            # Return empty Excel file
            buffer = BytesIO()
            df = pd.DataFrame({'url': []})
            df.to_excel(buffer, index=False, engine='openpyxl')
            buffer.seek(0)
            return buffer.getvalue()
        
        # Prepare data: flatten nested structures
        flattened_data = DataExporter._prepare_data_for_csv(data)
        
        if not flattened_data:
            buffer = BytesIO()
            df = pd.DataFrame({'url': []})
            df.to_excel(buffer, index=False, engine='openpyxl')
            buffer.seek(0)
            return buffer.getvalue()
        
        # Create DataFrame
        df = pd.DataFrame(flattened_data)
        
        # Ensure 'url' is the first column
        if 'url' in df.columns:
            cols = ['url'] + [c for c in df.columns if c != 'url']
            df = df[cols]
        
        # Replace NaN with empty string
        df = df.fillna('')
        
        # Export to Excel
        buffer = BytesIO()
        df.to_excel(buffer, index=False, engine='openpyxl')
        buffer.seek(0)
        return buffer.getvalue()
