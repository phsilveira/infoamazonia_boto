import logging
from typing import Tuple, Dict, Optional, List
from openai import OpenAI
import googlemaps
from fastapi import HTTPException
from config import settings

logger = logging.getLogger(__name__)

client = OpenAI(api_key=settings.OPENAI_API_KEY)
gmaps = googlemaps.Client(key=settings.GOOGLEMAPS_API_KEY)

SYSTEM_PROMPT = """Você é um sistema responsável por validar e corrigir nomes de regiões e localidades brasileiras da Amazonia legal.
Analise se o nome está correto e completo, considerando critérios oficiais e possíveis variações.

Para cada localidade fornecida:
1. Verifique se é um nome oficial (IBGE ou outras instituições)
2. Corrija abreviações para o nome completo
3. Considere sinônimos reconhecidos
4. Corrija erros de digitação
5. Para distritos, use o município correspondente

Formato de Saída:
T;[Nome Corrigido];[Tipo] - para localidade válida
F;[Nome Original];inexistente - para localidade inválida"""

def validate_brazilian_location(user_input: str, system_prompt: str = SYSTEM_PROMPT) -> Tuple[bool, str, str]:
    """Validates if the user input is a valid Brazilian city or region name.

    Args:
        user_input: The text expression to validate.
        system_prompt: The system prompt to use for validation.

    Returns:
        Tuple of (is_valid, name, region_type)
        - is_valid: True if location is valid (even with typos)
        - name: corrected name if valid, original input if invalid
        - region_type: region classification or 'inexistente' if invalid
    """
    try:
        completion = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input}
            ]
        )
        response = completion.choices[0].message.content.strip()
        is_valid, name, region_type = response.split(";", 2)

        return (True, name.strip(), region_type.strip()) if is_valid.strip() == "T" else (False, user_input, 'inexistente')
    except Exception as e:
        logger.error(f"Error validating location '{user_input}': {str(e)}")
        return (False, user_input, 'erro_sistema')

def validate_locations(location_text: str) -> List[Tuple[bool, str, str]]:
    """Validates multiple locations separated by commas.

    Args:
        location_text: String containing one or more locations separated by commas.

    Returns:
        List of (is_valid, name, region_type) tuples for each location.
    """
    # Check for "all locations" variations
    all_locations_variations = [
        "todas", "todos", "todas as", "all",
        "todas as localizações", "todas localizações", "all locations"
    ]

    if any(location_text.lower().strip().startswith(v) for v in all_locations_variations):
        return [(True, "ALL_LOCATIONS", "all")]

    # Split and validate individual locations
    locations = [loc.strip() for loc in location_text.split(',') if loc.strip()]
    if not locations:
        return [(False, location_text, 'inexistente')]

    results = []
    for location in locations:
        is_valid, name, region_type = validate_brazilian_location(location)
        results.append((is_valid, name, region_type))

    return results if results else [(False, location_text, 'inexistente')]

async def get_location_details(location_text: str) -> List[Dict]:
    """Gets location details including coordinates for multiple locations using Google Maps API."""
    try:
        locations_info = []
        validation_results = validate_locations(location_text)

        # Handle "all locations" case
        if len(validation_results) == 1 and validation_results[0][1] == "ALL_LOCATIONS":
            return [{
                "address": "All Locations",
                "latitude": None,
                "longitude": None,
                "corrected_name": "All Locations"
            }]

        # Get details for valid locations
        for is_valid, name, _ in validation_results:
            if not is_valid:
                continue

            geocode_result = gmaps.geocode(f"{name}, Brasil")
            if not geocode_result:
                continue

            location = geocode_result[0]['geometry']['location']
            address = geocode_result[0]['formatted_address']

            locations_info.append({
                "address": address,
                "latitude": location['lat'],
                "longitude": location['lng'],
                "corrected_name": name
            })

        if not locations_info:
            raise HTTPException(status_code=400, detail="No valid locations found")

        return locations_info
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting location details: {str(e)}")