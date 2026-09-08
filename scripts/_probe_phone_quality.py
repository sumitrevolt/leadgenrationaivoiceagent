import logging
import sys

logging.disable(logging.CRITICAL)
sys.path.insert(0, ".")
import phonenumbers

from app.telephony.dial_gate import _last10, phone_quality

nums = ['916436551963','916124696567','918312472948','918048054887','917126684222','+919876543210']
for n in nums:
    p = phonenumbers.parse('+91' + n[-10:], 'IN')
    print(n, '| last10=', _last10(n), '| valid=', phonenumbers.is_valid_number(p),
          '| type=', phonenumbers.number_type(p), '| quality=', phone_quality(n))
