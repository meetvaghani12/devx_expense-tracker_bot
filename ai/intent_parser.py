"""
Agent 1: Intent Parser
Converts raw natural language text into a structured IntentResult JSON
using Groq's Llama 3.3 70B model.
"""
import json
import logging
from groq import AsyncGroq
from config import GROQ_API_KEY

logger = logging.getLogger(__name__)

_client = None


def _get_client() -> AsyncGroq:
    global _client
    if _client is None:
        _client = AsyncGroq(api_key=GROQ_API_KEY)
    return _client


SYSTEM_PROMPT = """You are a financial intent parser for a group expense-splitting Telegram bot called SplitBot.
The group uses Indian Rupees (₹).

The sender's registered name is: "{sender_name}"
Today's date: {date_iso}
All registered users in this group:
{users_list}

The user may write in ANY language (English, Gujarati, Hindi, etc.). Understand the message regardless of language and always return the JSON response in English.

NUMBER WORD CONVERSION — always convert spoken/written number words to digits:
- Gujarati: એક=1, બે=2, ત્રણ=3, ચાર=4, પાંચ=5, છ=6, સાત=7, આઠ=8, નવ=9, દસ=10, વીસ=20, ત્રીસ=30, ચાળીસ=40, પચાસ=50, સાઠ=60, સિત્તેર=70, એંસી=80, નેવું=90, સો=100, બસો=200, ત્રણસો=300, પાંચસો=500, હજાર=1000
- Hindi: एक=1, दो=2, तीन=3, सौ=100, दो सौ=200, पाँच सौ=500, हज़ार=1000
- Combine correctly: "બે સો" or "બસો" = 200, "પાંચ સો" = 500, "બે હજાર" = 2000

Extract the user's intent and return ONLY a valid JSON object. No explanation, no markdown, no text outside the JSON.

INTENT TYPES:
- "add_expense"   : someone paid for something to be split among the group
- "settle"        : recording a payment between two people
- "check_balance" : user wants to know balances
- "check_history" : user wants to see recent expenses
- "unknown"       : cannot determine intent

SPLIT TYPES (for add_expense):
- "equal"   : divide equally
- "custom"  : different explicit amounts per person
- "percent" : percentage-based split

IMPORTANT RULES:
1. If sender says "I paid" or "I spent" (or Gujarati equivalent like "મે ચૂકવ્યા/ભર્યા/ચોકવ્યા") → paid_by_name = sender's name
2. "split with X and Y" OR "split between X and Y" → payer + X + Y all share equally (3-way). Debtors in splits = X and Y only (payer is NEVER in splits array — their share is implicit)
3. The payer is ALWAYS included in the headcount. splits array contains only the non-payers.
4. Match names aggressively — case-insensitive, partial, phonetic, and voice-transcription errors are all ok:
   - Prefix: "ken" → "Kenil", "mah" → "Mahil"
   - Phonetic/misspelled: "canil"→"Kenil", "meel"→"Meet", "maheel"→"Mahil", "akk"→"Ak"
   - Gujarati/Hindi transliteration: "કેનિલ"→"Kenil", "મહિલ"→"Mahil", "મીત"→"Meet"
   - Always pick the CLOSEST match from the known users list — do NOT give up easily
5. Only add to unresolved_names if you truly cannot find any similar name in the list
6. Only add to ambiguous_names if 2+ users are equally close matches
7. The payer is NEVER included in the splits array
8. Category must be one of: Food & Dining, Travel & Transport, Accommodation, Groceries, Entertainment, Utilities & Bills, Rent, Medical, Shopping, Other
9. Infer category from description if not stated (e.g. "dinner" → "Food & Dining", "petrol" → "Travel & Transport"). If category cannot be clearly inferred, use "Other" — do NOT default to "Food & Dining"
10. For equal split among ALL group members (excluding payer), set include_all_members = true and leave splits empty
11. CRITICAL — Always convert number words to digits before setting "amount". Examples: બસો/બે સો=200, ત્રણસો=300, ચારસો=400, પાંચસો=500, સો=100, હજાર=1000, બે હજાર=2000. दो सौ=200, पाँच सौ=500. Never guess — if the number word says 200, amount must be 200.0

RETURN THIS EXACT JSON STRUCTURE (use double braces since this is a Python format string):
{{
  "intent": "add_expense | settle | check_balance | check_history | unknown",
  "confidence": 0.0,
  "unresolved_names": [],
  "ambiguous_names": [],
  "data": {{
    "description": "string (for add_expense)",
    "amount": 0.0,
    "category": "string",
    "paid_by_name": "string (exact name from users list)",
    "split_type": "equal or custom or percent",
    "include_all_members": false,
    "splits": [
      {{"name": "string", "amount_owed": 0.0}}
    ],
    "note": null,
    "payer_name": "string (for settle)",
    "receiver_name": "string (for settle)",
    "method": "cash or upi or manual",
    "target_user_name": null
  }}
}}"""


class IntentParseError(Exception):
    pass


async def parse_intent(raw_text: str, sender_name: str, known_users: list, date_iso: str) -> dict:
    """
    Calls Groq Llama 3.3 70B to parse raw_text into a structured IntentResult.
    Returns dict matching the JSON schema above.
    Raises IntentParseError on failure.
    """
    users_list = "\n".join(f"  - {u['name']}" for u in known_users)

    system = SYSTEM_PROMPT.format(
        sender_name=sender_name,
        date_iso=date_iso,
        users_list=users_list,
    )

    client = _get_client()
    try:
        response = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": raw_text},
            ],
            temperature=0,
            max_tokens=600,
        )
        raw_json = response.choices[0].message.content.strip()

        # Strip markdown code fences if model added them
        if raw_json.startswith("```"):
            raw_json = raw_json.split("```")[1]
            if raw_json.startswith("json"):
                raw_json = raw_json[4:]
            raw_json = raw_json.strip()

        result = json.loads(raw_json)
        logger.info(f"NL parse: intent={result.get('intent')} confidence={result.get('confidence')} for: {raw_text[:60]}")
        return result

    except json.JSONDecodeError as e:
        logger.error(f"Intent parser returned invalid JSON: {e}")
        raise IntentParseError(f"JSON parse failed: {e}")
    except Exception as e:
        logger.error(f"Intent parser error: {e}")
        raise IntentParseError(str(e))
