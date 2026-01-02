"""
Phone Validator
Validates and formats phone numbers
"""
import re
from typing import Optional, Tuple
from dataclasses import dataclass


@dataclass
class PhoneInfo:
    """Phone number information"""
    original: str
    formatted: str
    country_code: str
    national_number: str
    is_valid: bool
    is_mobile: bool
    carrier: Optional[str] = None
    region: Optional[str] = None


class PhoneValidator:
    """
    Validates and formats Indian and international phone numbers
    """
    
    # Indian mobile prefixes
    INDIAN_MOBILE_PREFIXES = [
        '6', '7', '8', '9'  # All Indian mobiles start with these
    ]
    
    # Indian carrier identification (first 4 digits after country code)
    INDIAN_CARRIERS = {
        # Jio
        '6000': 'Jio', '6001': 'Jio', '6002': 'Jio', '6003': 'Jio',
        '7000': 'Jio', '7001': 'Jio', '7002': 'Jio',
        # Airtel
        '7015': 'Airtel', '7018': 'Airtel', '8010': 'Airtel',
        '9810': 'Airtel', '9811': 'Airtel', '9812': 'Airtel',
        # Vi (Vodafone Idea)
        '7016': 'Vi', '7017': 'Vi', '8011': 'Vi',
        '9820': 'Vi', '9821': 'Vi', '9822': 'Vi',
        # BSNL
        '9415': 'BSNL', '9416': 'BSNL', '9417': 'BSNL',
    }
    
    # State/Circle codes (first 3-4 digits)
    INDIAN_REGIONS = {
        '011': 'Delhi',
        '022': 'Mumbai',
        '033': 'Kolkata',
        '044': 'Chennai',
        '080': 'Bangalore',
        '040': 'Hyderabad',
        '079': 'Ahmedabad',
        '020': 'Pune',
        '0141': 'Jaipur',
        '0522': 'Lucknow',
    }
    
    @classmethod
    def validate(cls, phone: str) -> PhoneInfo:
        """
        Validate and get info about a phone number
        
        Args:
            phone: Phone number string
        
        Returns:
            PhoneInfo with validation details
        """
        original = phone
        
        # Clean the number
        cleaned = cls._clean_number(phone)
        
        if not cleaned:
            return PhoneInfo(
                original=original,
                formatted="",
                country_code="",
                national_number="",
                is_valid=False,
                is_mobile=False
            )
        
        # Determine if it's Indian
        country_code, national = cls._extract_country_code(cleaned)
        
        # Validate based on country
        if country_code == "91":
            return cls._validate_indian(original, cleaned, national)
        else:
            return cls._validate_international(original, cleaned, country_code, national)
    
    @classmethod
    def _clean_number(cls, phone: str) -> str:
        """Remove all non-digit characters"""
        return re.sub(r'\D', '', phone)
    
    @classmethod
    def _extract_country_code(cls, cleaned: str) -> Tuple[str, str]:
        """Extract country code from number"""
        # Check for common country codes
        if cleaned.startswith('91') and len(cleaned) >= 12:
            return ('91', cleaned[2:])
        elif cleaned.startswith('1') and len(cleaned) == 11:
            return ('1', cleaned[1:])
        elif cleaned.startswith('44') and len(cleaned) >= 12:
            return ('44', cleaned[2:])
        elif len(cleaned) == 10:
            # Assume Indian without country code
            return ('91', cleaned)
        else:
            return ('', cleaned)
    
    @classmethod
    def _validate_indian(cls, original: str, cleaned: str, national: str) -> PhoneInfo:
        """Validate Indian phone number"""
        is_valid = False
        is_mobile = False
        carrier = None
        region = None
        
        if len(national) == 10:
            first_digit = national[0]
            
            if first_digit in cls.INDIAN_MOBILE_PREFIXES:
                is_valid = True
                is_mobile = True
                
                # Try to identify carrier
                prefix = national[:4]
                carrier = cls.INDIAN_CARRIERS.get(prefix)
            
            elif first_digit == '0':
                # Landline with STD code
                for code, reg in cls.INDIAN_REGIONS.items():
                    if national.startswith(code):
                        is_valid = True
                        region = reg
                        break
        
        formatted = f"+91{national}" if is_valid else ""
        
        return PhoneInfo(
            original=original,
            formatted=formatted,
            country_code="91",
            national_number=national,
            is_valid=is_valid,
            is_mobile=is_mobile,
            carrier=carrier,
            region=region
        )
    
    @classmethod
    def _validate_international(
        cls,
        original: str,
        cleaned: str,
        country_code: str,
        national: str
    ) -> PhoneInfo:
        """Validate international phone number"""
        # Basic validation - at least 7 digits
        is_valid = len(national) >= 7 and len(national) <= 15
        
        formatted = f"+{country_code}{national}" if is_valid and country_code else ""
        
        return PhoneInfo(
            original=original,
            formatted=formatted,
            country_code=country_code,
            national_number=national,
            is_valid=is_valid,
            is_mobile=True  # Assume mobile for international
        )
    
    @classmethod
    def format_for_display(cls, phone: str) -> str:
        """Format phone number for display"""
        info = cls.validate(phone)
        
        if not info.is_valid:
            return phone
        
        if info.country_code == "91":
            # Indian format: +91 98765 43210
            national = info.national_number
            return f"+91 {national[:5]} {national[5:]}"
        else:
            return info.formatted
    
    @classmethod
    def format_for_dialing(cls, phone: str, from_india: bool = True) -> str:
        """Format phone number for dialing"""
        info = cls.validate(phone)
        
        if not info.is_valid:
            return phone
        
        if from_india:
            if info.country_code == "91":
                return info.national_number
            else:
                return f"00{info.country_code}{info.national_number}"
        else:
            return info.formatted
    
    @classmethod
    def is_valid_indian_mobile(cls, phone: str) -> bool:
        """Quick check if phone is a valid Indian mobile"""
        info = cls.validate(phone)
        return info.is_valid and info.is_mobile and info.country_code == "91"
    
    @classmethod
    def mask_phone(cls, phone: str) -> str:
        """Mask phone number for privacy"""
        info = cls.validate(phone)
        
        if not info.is_valid:
            return "****"
        
        national = info.national_number
        if len(national) >= 10:
            return f"+{info.country_code} {national[:2]}****{national[-2:]}"
        return "****"
