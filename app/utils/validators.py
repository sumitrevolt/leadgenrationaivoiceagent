"""
Input Validation Utilities
Centralized validation functions for API inputs
"""
import re
from typing import Optional, List, Tuple
from datetime import datetime, time
import phonenumbers
from phonenumbers import NumberParseException


def validate_phone_number(
    phone: str,
    default_region: str = "IN"
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validate and format phone number using phonenumbers library
    
    Args:
        phone: Phone number string
        default_region: Default country code (IN for India)
        
    Returns:
        Tuple of (is_valid, formatted_number, error_message)
    """
    if not phone:
        return False, None, "Phone number is required"
    
    try:
        # Parse the phone number
        parsed = phonenumbers.parse(phone, default_region)
        
        # Check if it's a valid number
        if not phonenumbers.is_valid_number(parsed):
            return False, None, "Invalid phone number"
        
        # Format to E.164 international format
        formatted = phonenumbers.format_number(
            parsed,
            phonenumbers.PhoneNumberFormat.E164
        )
        
        return True, formatted, None
        
    except NumberParseException as e:
        return False, None, f"Could not parse phone number: {str(e)}"


def validate_email(email: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validate email format
    
    Args:
        email: Email string
        
    Returns:
        Tuple of (is_valid, normalized_email, error_message)
    """
    if not email:
        return False, None, "Email is required"
    
    # Basic email pattern
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    email = email.strip().lower()
    
    if not re.match(pattern, email):
        return False, None, "Invalid email format"
    
    # Check for common typos
    if email.endswith('.con'):
        return False, None, "Did you mean .com?"
    
    return True, email, None


def validate_url(url: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validate URL format
    
    Args:
        url: URL string
        
    Returns:
        Tuple of (is_valid, normalized_url, error_message)
    """
    if not url:
        return True, None, None  # URL is optional
    
    url = url.strip()
    
    # Add https:// if no protocol
    if not url.startswith(('http://', 'https://')):
        url = f'https://{url}'
    
    # Basic URL pattern
    pattern = r'^https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(/.*)?$'
    
    if not re.match(pattern, url):
        return False, None, "Invalid URL format"
    
    return True, url, None


def validate_indian_pincode(pincode: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validate Indian pincode
    
    Args:
        pincode: Pincode string
        
    Returns:
        Tuple of (is_valid, normalized_pincode, error_message)
    """
    if not pincode:
        return True, None, None  # Pincode is optional
    
    pincode = pincode.strip()
    
    # Indian pincode is exactly 6 digits and doesn't start with 0
    if not re.match(r'^[1-9][0-9]{5}$', pincode):
        return False, None, "Invalid Indian pincode (should be 6 digits, not starting with 0)"
    
    return True, pincode, None


def validate_time_range(
    start_time: str,
    end_time: str
) -> Tuple[bool, Optional[time], Optional[time], Optional[str]]:
    """
    Validate and parse time range
    
    Args:
        start_time: Start time in HH:MM format
        end_time: End time in HH:MM format
        
    Returns:
        Tuple of (is_valid, parsed_start, parsed_end, error_message)
    """
    try:
        start = datetime.strptime(start_time, "%H:%M").time()
        end = datetime.strptime(end_time, "%H:%M").time()
        
        if start >= end:
            return False, None, None, "Start time must be before end time"
        
        return True, start, end, None
        
    except ValueError:
        return False, None, None, "Invalid time format. Use HH:MM"


def validate_date(
    date_str: str,
    formats: List[str] = None
) -> Tuple[bool, Optional[datetime], Optional[str]]:
    """
    Validate and parse date string
    
    Args:
        date_str: Date string
        formats: List of allowed formats
        
    Returns:
        Tuple of (is_valid, parsed_date, error_message)
    """
    if not date_str:
        return False, None, "Date is required"
    
    formats = formats or [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%Y/%m/%d",
        "%d %b %Y",
        "%d %B %Y",
    ]
    
    for fmt in formats:
        try:
            parsed = datetime.strptime(date_str.strip(), fmt)
            return True, parsed, None
        except ValueError:
            continue
    
    return False, None, f"Invalid date format. Expected formats: {', '.join(formats[:3])}"


def validate_password(password: str) -> Tuple[bool, List[str]]:
    """
    Validate password strength
    
    Args:
        password: Password string
        
    Returns:
        Tuple of (is_valid, list_of_issues)
    """
    issues = []
    
    if len(password) < 8:
        issues.append("Password must be at least 8 characters long")
    
    if not re.search(r'[A-Z]', password):
        issues.append("Password must contain at least one uppercase letter")
    
    if not re.search(r'[a-z]', password):
        issues.append("Password must contain at least one lowercase letter")
    
    if not re.search(r'\d', password):
        issues.append("Password must contain at least one digit")
    
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        issues.append("Password must contain at least one special character")
    
    return len(issues) == 0, issues


def sanitize_string(
    value: str,
    max_length: int = 500,
    allow_html: bool = False
) -> str:
    """
    Sanitize string input
    
    Args:
        value: Input string
        max_length: Maximum allowed length
        allow_html: Whether to allow HTML tags
        
    Returns:
        Sanitized string
    """
    if not value:
        return ""
    
    value = value.strip()
    
    if not allow_html:
        # Remove HTML tags
        value = re.sub(r'<[^>]+>', '', value)
    
    # Truncate if too long
    if len(value) > max_length:
        value = value[:max_length]
    
    return value


def validate_niche(niche: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validate niche/industry value
    
    Args:
        niche: Niche string
        
    Returns:
        Tuple of (is_valid, normalized_niche, error_message)
    """
    valid_niches = {
        'real_estate': ['real estate', 'realestate', 'property', 'realtor'],
        'solar': ['solar', 'solar energy', 'solar panel'],
        'education': ['education', 'edtech', 'training', 'coaching'],
        'insurance': ['insurance', 'life insurance', 'health insurance'],
        'digital_marketing': ['digital marketing', 'marketing', 'seo', 'digital agency'],
        'healthcare': ['healthcare', 'health', 'medical', 'clinic', 'hospital'],
        'logistics': ['logistics', 'transport', 'shipping', 'freight'],
        'manufacturing': ['manufacturing', 'factory', 'production'],
        'it_services': ['it', 'it services', 'software', 'technology'],
        'finance': ['finance', 'fintech', 'banking', 'investment'],
        'other': ['other', 'general'],
    }
    
    if not niche:
        return False, None, "Niche is required"
    
    niche_lower = niche.lower().strip()
    
    # Direct match
    if niche_lower in valid_niches:
        return True, niche_lower, None
    
    # Check aliases
    for canonical, aliases in valid_niches.items():
        if niche_lower in aliases:
            return True, canonical, None
    
    # Partial match
    for canonical, aliases in valid_niches.items():
        for alias in aliases:
            if alias in niche_lower or niche_lower in alias:
                return True, canonical, None
    
    # Return as 'other' if not found but allow it
    return True, 'other', None


def validate_city(city: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validate and normalize city name
    
    Args:
        city: City name string
        
    Returns:
        Tuple of (is_valid, normalized_city, error_message)
    """
    if not city:
        return False, None, "City is required"
    
    city = city.strip().title()
    
    # Common Indian city name corrections
    corrections = {
        'Bombay': 'Mumbai',
        'Madras': 'Chennai',
        'Calcutta': 'Kolkata',
        'Bangalore': 'Bengaluru',
        'Bengaluru': 'Bangalore',  # Both are acceptable
        'Gurgaon': 'Gurugram',
    }
    
    if city in corrections:
        city = corrections[city]
    
    # Basic validation - only letters, spaces, and hyphens
    if not re.match(r'^[A-Za-z\s\-]+$', city):
        return False, None, "City name can only contain letters, spaces, and hyphens"
    
    if len(city) < 2:
        return False, None, "City name is too short"
    
    return True, city, None
