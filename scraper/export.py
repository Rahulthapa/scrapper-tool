"""
Export layer for generating RFC-4180 compliant CSV files.
Ensures strict column ordering and proper formatting.
"""
import csv
import logging
from typing import List, Dict, Any
from pathlib import Path

from .config import ScraperConfig, CSV_COLUMNS

logger = logging.getLogger(__name__)


class CSVExporter:
    """Exports data to RFC-4180 compliant CSV"""
    
    def __init__(self, config: ScraperConfig):
        self.config = config
    
    def export(self, data: List[Dict[str, Any]], output_path: str = None) -> str:
        """
        Export normalized data to CSV file
        
        Args:
            data: List of normalized dictionaries
            output_path: Output file path (uses config default if None)
        
        Returns:
            Path to created CSV file
        """
        if output_path is None:
            output_path = self.config.csv_output_path
        
        # Ensure output directory exists
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Write CSV
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(
                f,
                fieldnames=CSV_COLUMNS,
                quoting=csv.QUOTE_MINIMAL,
                escapechar='\\',
                doublequote=True
            )
            
            # Write header
            writer.writeheader()
            
            # Write rows
            for row in data:
                # Ensure all columns are present
                csv_row = {}
                for column in CSV_COLUMNS:
                    value = row.get(column, "")
                    # Convert None to empty string
                    if value is None:
                        value = ""
                    # Ensure string type
                    csv_row[column] = str(value)
                
                writer.writerow(csv_row)
        
        logger.info(f"Exported {len(data)} rows to {output_file}")
        return str(output_file)
    
    def validate_data(self, data: List[Dict[str, Any]]) -> bool:
        """
        Validate that data has all required columns
        
        Returns:
            True if valid, False otherwise
        """
        if not data:
            logger.warning("No data to validate")
            return False
        
        missing_columns = []
        for column in CSV_COLUMNS:
            if column not in data[0]:
                missing_columns.append(column)
        
        if missing_columns:
            logger.error(f"Missing columns: {missing_columns}")
            return False
        
        return True

