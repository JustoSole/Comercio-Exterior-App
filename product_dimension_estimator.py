import json
import re
import os
import base64
import logging
import requests
import toml
from typing import Dict, Any, Tuple, Optional
from bs4 import BeautifulSoup

# --- OpenAI Integration ---
try:
    import openai
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def get_api_key_from_secrets(key_name: str) -> Optional[str]:
    """Helper function to get API key from secrets or environment"""
    try:
        # Try loading from .streamlit/secrets.toml
        secrets_path = os.path.join('.streamlit', 'secrets.toml')
        if os.path.exists(secrets_path):
            secrets = toml.load(secrets_path)
            return secrets.get('api_keys', {}).get(key_name)
        
        # Fallback to environment variable
        return os.environ.get(key_name)
    except Exception:
        return os.environ.get(key_name)

def parse_and_convert_weight(weight_str: str) -> Optional[float]:
    """Parses a weight string (e.g., '1.5kg', '500g') and converts it to kilograms."""
    if not weight_str:
        return None
    
    weight_str = str(weight_str).lower().replace(',', '.')
    
    match = re.search(r'(\d+(?:\.\d+)?)\s*(kg|g|lbs|oz|kilogram|gram|pound|ounce)?', weight_str)
    
    if not match:
        return None
        
    try:
        value = float(match.group(1))
        unit = match.group(2)
        
        if unit in ['g', 'gram']:
            return value / 1000.0
        if unit in ['lbs', 'pound']:
            return value * 0.453592
        if unit in ['oz', 'ounce']:
            return value * 0.0283495
        if unit in ['kg', 'kilogram']:
            return value
        
        if not unit:
            if value > 50:
                return value / 1000.0
            else:
                return value
                
    except (ValueError, IndexError):
        return None
        
    return None

def validate_dimensions(dimensions: Dict[str, float]) -> bool:
    """Performs a sanity check on extracted dimensions."""
    if not dimensions or not all(k in dimensions for k in ['length_cm', 'width_cm', 'height_cm']):
        return False
    
    # Check for absurdly large values (e.g., > 5 meters), which are likely package/pallet sizes.
    MAX_DIM_CM = 500 
    for dim in dimensions.values():
        if not isinstance(dim, (int, float)) or dim <= 0 or dim > MAX_DIM_CM:
            logger.warning(f"Invalid dimension detected and rejected: {dimensions}")
            return False
            
    # Check that volume is not zero
    if dimensions['length_cm'] * dimensions['width_cm'] * dimensions['height_cm'] == 0:
        logger.warning(f"Invalid zero-volume dimension detected: {dimensions}")
        return False

    return True


def get_api_key_from_secrets(key_name: str) -> str:
    """Loads an API key from the .streamlit/secrets.toml file."""
    # Construct path relative to this file's location
    base_dir = os.path.dirname(os.path.abspath(__file__))
    secrets_path = os.path.join(base_dir, '.streamlit', 'secrets.toml')
    
    if not os.path.exists(secrets_path):
        logger.warning(f"Secrets file not found at {secrets_path}")
        return ""
    try:
        secrets = toml.load(secrets_path)
        return secrets.get('api_keys', {}).get(key_name, "")
    except Exception as e:
        logger.error(f"Error reading secrets.toml: {e}")
        return ""

# --- Helper Functions for Data Extraction ---

def extract_from_attributes(product: Dict[str, Any]) -> Tuple[Optional[str], Optional[Dict[str, float]]]:
    """Tries to extract weight and dimensions from a product's structured attributes."""
    weight = None
    dimensions = None
    
    attribute_lists = [
        product.get('productProperties', []),
        product.get('productKeyIndustryProperties', []),
        product.get('productOtherProperties', []),
        product.get('productBasicProperties', []) # Adding another common list
    ]
    
    for attr_list in attribute_lists:
        if not isinstance(attr_list, list): continue
        for attr in attr_list:
            if not isinstance(attr, dict): continue
            attr_name = attr.get('attrName', '').lower()
            attr_value = attr.get('attrValue', '')
            
            if 'weight' in attr_name and not weight:
                weight = attr_value
            # Placeholder for dimension extraction from attributes
            if any(dim_key in attr_name for dim_key in ['size', 'dimensions']) and not dimensions:
                dimensions = parse_and_convert_dimensions(attr_value)
            
    return weight, dimensions

def extract_from_html(product: Dict[str, Any]) -> Tuple[Optional[str], Optional[Dict[str, float]]]:
    """
    Tries to extract weight and dimensions from the product's HTML description,
    with intelligent table parsing.
    """
    html_description = product.get('productHtmlDescription', '')
    if not html_description:
        return None, None

    soup = BeautifulSoup(html_description, 'html.parser')
    
    # --- 1. Intelligent Table Parsing ---
    title = product.get('subject', '').lower()
    # Extract keywords like "65 inch" or "65\"" from the title
    title_keywords = re.findall(r'(\d+)\s*(?:inch|")', title)
    
    table_dims = None
    if title_keywords:
        keyword = title_keywords[0]
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                row_text = row.get_text(separator=' ', strip=True).lower()
                if f"{keyword} inches" in row_text or f" {keyword} " in row_text:
                    dims_in_row = parse_and_convert_dimensions(row.get_text())
                    if dims_in_row:
                        logger.info(f"Found dimensions in table for keyword '{keyword}': {dims_in_row}")
                        table_dims = dims_in_row
                        break
            if table_dims:
                break

    # --- 2. Regex on Plain Text (Fallback) ---
    plain_text = soup.get_text(separator=' ', strip=True)
    
    # Weight extraction
    weight_match = re.search(r'(\d+(?:\.\d+)?(?:-d+(?:\.\d+)?)?)\s*kg', plain_text, re.IGNORECASE)
    weight = weight_match.group(1).split('-')[0] + 'kg' if weight_match else None

    # Dimension extraction (use table dims if found, otherwise fallback to regex on whole text)
    final_dimensions = table_dims if table_dims else parse_and_convert_dimensions(plain_text)
    
    return weight, final_dimensions

def parse_and_convert_dimensions(text: str) -> Optional[Dict[str, float]]:
    """Helper to find and parse dimensions from a string and convert to cm."""
    if not text:
        return None
    
    text = str(text).lower().replace(',', '.')
    
    # Define units and their multipliers to cm
    unit_map = {
        'inch': 2.54, '"': 2.54, 'in': 2.54,
        'foot': 30.48, 'ft': 30.48,
        'meter': 100.0, 'm': 100.0,
        'cm': 1.0
    }
    # Sort keys by length to avoid partial matches (e.g., 'inch' before 'in')
    unit_keys_for_regex = r'|'.join(re.escape(k) for k in sorted(unit_map.keys(), key=len, reverse=True))

    # --- Global Unit Detection ---
    global_unit = None
    for unit_key in sorted(unit_map.keys(), key=len, reverse=True):
        if unit_key in text:
            global_unit = unit_key
            break

    # --- Pattern 1: LxWxH format ---
    pattern1 = re.compile(rf'(\d+(?:\.\d+)?)\s*[x×*]\s*(\d+(?:\.\d+)?)\s*[x×*]\s*(\d+(?:\.\d+)?)\s*({unit_keys_for_regex})?')
    match1 = pattern1.search(text)
    
    if match1:
        try:
            l, w, h = float(match1.group(1)), float(match1.group(2)), float(match1.group(3))
            unit = match1.group(4) or global_unit or 'cm'
            multiplier = unit_map.get(unit, 1.0)
            return {"length_cm": l * multiplier, "width_cm": w * multiplier, "height_cm": h * multiplier}
        except (ValueError, IndexError):
            pass

    # --- Pattern 2: Key-value format ---
    dims = {}
    found_any = False
    for dim_name in ['length', 'width', 'height']:
        pattern2 = re.compile(rf'{dim_name}\s*[:=]?\s*(\d+(?:\.\d+)?)\s*({unit_keys_for_regex})?')
        match2 = pattern2.search(text)
        if match2:
            try:
                value = float(match2.group(1))
                unit = match2.group(2) or global_unit or 'cm'
                multiplier = unit_map.get(unit, 1.0)
                dims[f'{dim_name}_cm'] = value * multiplier
                found_any = True
            except (ValueError, IndexError):
                continue
    
    if len(dims) == 3:
        return dims

    if found_any:
        logger.warning(f"Found partial dimensions in '{text}', but not all three. Discarding.")

    return None


# --- Main Estimator Classes ---

SYSTEM_PROMPT_DIMENSIONS = """
You are a world-class logistics expert specializing in e-commerce fulfillment. Your sole task is to analyze product data and an image to provide precise and realistic shipping estimates.

**CRITICAL INSTRUCTIONS:**
1.  **Analyze Holistically:** Synthesize the product's title, categories, and attributes with the visual information from the image. Use objects in the image for scale.
2.  **Estimate for Shipping:** Your output must be the dimensions and weight of the **product inside its final shipping package** (e.g., a sturdy cardboard box with protective filler). The dimensions should be slightly larger than the product itself.
3.  **Handle Partial Data:** If I provide partial information (e.g., "the weight is known to be 2.5kg"), you MUST use that information and estimate only the missing values.
4.  **Strict JSON Output:** Your response MUST be a valid JSON object and nothing else. Do not include markdown, comments, or any introductory text.

**JSON Schema:**
{
  "length_cm": <float>,
  "width_cm": <float>,
  "height_cm": <float>,
  "weight_kg": <float>
}
"""

class AIDimensionEstimator:
    """Estimates product dimensions and weight using an LLM."""
    
    def __init__(self, api_key: str = None):
        if not OPENAI_AVAILABLE:
            raise ImportError("OpenAI library not installed. Please run: pip install openai")
        
        self.api_key = api_key or get_api_key_from_secrets("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key is required and was not found.")
        
        self.client = OpenAI(api_key=self.api_key)
        logger.info("AI Dimension Estimator initialized.")

    def _download_image_to_base64(self, url: str) -> str:
        """Downloads an image and returns it as a base64 string."""
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return base64.b64encode(response.content).decode('utf-8')
        except requests.RequestException as e:
            logger.error(f"Error downloading image from {url}: {e}")
            raise

    def estimate(self, prompt_data: dict, partial_data: dict = None) -> dict:
        """Estimates dimensions and weight for a single product, using partial data if available."""
        subject = prompt_data.get('subject', 'No title')
        logger.info(f"Estimating dimensions via LLM for: {subject[:100]}...")

        image_data = None
        if prompt_data.get('image_urls'):
            first_image_url = prompt_data['image_urls'][0]
            try:
                image_data = self._download_image_to_base64(first_image_url)
                logger.info(f"Successfully processed image from URL: {first_image_url[:100]}")
            except Exception as img_error:
                logger.warning(f"Failed to download or process image: {img_error}")

        # Build a more context-rich description
        description = f"Product Title: {subject}\n"
        description += f"Categories: {', '.join(prompt_data.get('categories', []))}\n"

        if partial_data:
            description += "\n**KNOWN INFORMATION (Use this and estimate the rest):**\n"
            if partial_data.get('weight_kg'):
                description += f"- The item's weight is {partial_data['weight_kg']} kg.\n"
            if partial_data.get('dimensions_cm'):
                dims = partial_data['dimensions_cm']
                description += f"- The item's dimensions are {dims.get('length_cm')}x{dims.get('width_cm')}x{dims.get('height_cm')} cm.\n"

        description += f"\n**PRODUCT DETAILS FROM PAGE:**\n"
        description += f"SKU Attributes: {json.dumps(prompt_data.get('sku', []))}\n"
        description += f"HTML Description Snippet: {prompt_data.get('description_snippet', '')}"

        user_content = [{"type": "text", "text": description}]
        if image_data:
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image_data}", "detail": "high"}
            })
        
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT_DIMENSIONS},
            {"role": "user", "content": user_content}
        ]

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0,
                response_format={"type": "json_object"}
            )
            response_text = response.choices[0].message.content
            logger.info(f"Received LLM estimation: {response_text}")
            return json.loads(response_text)
        except Exception as e:
            logger.error(f"An error occurred during LLM estimation for '{subject[:50]}...': {e}")
            return {"error": str(e)}

class ProductShippingEstimator:
    """
    Orchestrates extraction and AI estimation of product shipping details.
    """
    def __init__(self, api_key: str = None):
        self.ai_estimator = AIDimensionEstimator(api_key=api_key)


    def get_shipping_details(self, product_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main method to get shipping details for a product.
        Tries extraction, validates it, and intelligently falls back to AI estimation.
        """
        # 1. Direct Extraction
        weight_attr, dim_attr = extract_from_attributes(product_data)
        weight_html, dim_html = extract_from_html(product_data)
        
        final_weight_str = weight_html or weight_attr
        final_dimensions = dim_html or dim_attr
        
        # 2. Validation of Extracted Data
        are_dimensions_valid = validate_dimensions(final_dimensions)
        
        final_weight_kg = parse_and_convert_weight(final_weight_str)
        if not final_weight_kg:
            logger.warning(f"Could not parse a valid weight from '{final_weight_str}'.")
        
        is_weight_valid = final_weight_kg is not None and final_weight_kg > 0
        
        # If we have complete and valid data, we're done.
        if is_weight_valid and are_dimensions_valid:
            logger.info(f"Successfully extracted and validated shipping info for '{product_data.get('subject', 'N/A')[:50]}...'")
            return {
                "weight_kg": final_weight_kg,
                "dimensions_cm": final_dimensions,
                "method": "extracted_validated"
            }

        # 3. LLM Estimation (Fallback)
        logger.warning(f"Extracted data incomplete or invalid. Weight valid: {is_weight_valid}, Dims valid: {are_dimensions_valid}. Proceeding with AI.")
        
        partial_data = {}
        if is_weight_valid:
            partial_data['weight_kg'] = final_weight_kg
        
        prompt_data = {
            'subject': product_data.get('subject'),
            'categories': product_data.get('categories', []),
            'sku': product_data.get('sku', {}).get('skuAttrs', []),
            'image_urls': [item['imageUrl']['big'] for item in product_data.get('mediaItems', []) if isinstance(item, dict) and item.get('type') == 'image' and item.get('imageUrl')],
            'description_snippet': product_data.get('productHtmlDescription', '')[:500]
        }
        
        estimation = self.ai_estimator.estimate(prompt_data, partial_data)
        
        if 'error' not in estimation:
            return {
                "weight_kg": estimation.get('weight_kg'),
                "dimensions_cm": {
                    'length_cm': estimation.get('length_cm'),
                    'width_cm': estimation.get('width_cm'),
                    'height_cm': estimation.get('height_cm')
                },
                "method": "llm_estimated"
            }
        else:
            # If LLM fails, return what we have, plus the error
            return {
                "weight_kg": final_weight_kg if is_weight_valid else None,
                "dimensions_cm": final_dimensions if are_dimensions_valid else None,
                "error": estimation.get('error'),
                "method": "extraction_failed_llm_failed"
            }


if __name__ == '__main__':
    """
    Standalone execution to process a file of products.
    This demonstrates the class usage and preserves the original script's functionality.
    """
    print("Running Product Dimension Estimator as a standalone script...")
    
    try:
        estimator = ProductShippingEstimator()
        
        script_dir = os.path.dirname(os.path.abspath(__file__))
        input_file = os.path.join(script_dir, 'apify_results', 'dataset_scrape-alibaba-item_2025-07-06_16-21-14-335.json')
        output_file = os.path.join(script_dir, 'apify_results', 'final_estimated_products_standalone.json')
        
        if not os.path.exists(input_file):
            print(f"Error: Input file not found at {input_file}")
            exit()
            
        with open(input_file, 'r') as f:
            products = json.load(f)
        
        processed_products = []
        for i, product in enumerate(products, 1):
            print(f"\n--- Processing product {i}/{len(products)}: {product.get('subject', 'N/A')[:60]}...")
            shipping_details = estimator.get_shipping_details(product)
            product['shipping_estimation'] = shipping_details
            processed_products.append(product)

        with open(output_file, 'w') as f:
            json.dump(processed_products, f, indent=2)
            
        print(f"\n✅ Processing complete. Full results saved to {output_file}")

    except (ImportError, ValueError) as e:
        logger.error(f"Initialization Failed: {e}")
        logger.error("Please ensure 'openai' and 'toml' libraries are installed ('pip install openai toml') and your OPENAI_API_KEY is set in .streamlit/secrets.toml") 