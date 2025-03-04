import logging
from typing import Tuple, Dict, Optional, List
from openai import OpenAI
import googlemaps
from fastapi import HTTPException
from config import settings

client = OpenAI(api_key=settings.OPENAI_API_KEY)
gmaps = googlemaps.Client(key=settings.GOOGLEMAPS_API_KEY)

SYSTEM_PROMPT = """Você é um sistema responsável por validar e corrigir nomes de regiões e localidades brasileiras da Amazonia legal.
Seu objetivo é analisar se o usuário digitou corretamente os nomes de uma ou mais regiões, considerando critérios oficiais e possíveis variações.

Critérios de Validação:
    1. Nomes Oficiais: Baseie-se nos nomes oficiais definidos pelo IBGE ou outras instituições relevantes.
    2. Abreviações Comuns: Aceite abreviações amplamente reconhecidas, mas prefira corrigir para o nome completo.
    3. Sinônimos: Considere nomes alternativos ou sinônimos reconhecidos para a mesma localidade ou região.
    4. Erros de Digitação: Identifique e sugira correções para erros ortográficos ou variações de escrita.
    5. Menor Nível Geográfico: A menor unidade válida é um município.
    6. Múltiplas Localidades: O usuário pode inserir múltiplas localidades separadas por vírgula.

Formato de Saída para múltiplas localidades:
    Para cada localidade na lista:
    • T;<Nome Corrigido>;<Classificação> para entradas válidas
    • F;<Nome Original>;<Classificação> para entradas inválidas
    Separe cada resultado com '|' quando houver múltiplas localidades."""

async def validate_brazilian_location(location_text: str) -> List[Tuple[bool, str, str]]:
    """Validates if the input contains valid Brazilian city or region names.
    Returns a list of tuples (is_valid, corrected_name, region_type) for each location."""
    try:
        # Split the input text by commas and clean each location name
        locations = [loc.strip() for loc in location_text.split(',') if loc.strip()]

        # If no valid locations found, return the original as invalid
        if not locations:
            return [(False, location_text, 'inexistente')]

        completion = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": location_text}
            ]
        )
        response = completion.choices[0].message.content

        # Process multiple locations
        results = []
        for location_result in response.split('|'):
            is_valid, name, region_type = location_result.strip().split(';', 2)
            results.append((is_valid.strip() == "T", name.strip(), region_type.strip()))

        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error validating locations: {str(e)}")

async def get_location_details(location_text: str, country: str = "BR") -> List[Dict]:
    """Gets location details including coordinates for multiple locations using Google Maps API."""
    try:
        locations_info = []
        validation_results = await validate_brazilian_location(location_text)

        for is_valid, corrected_name, _ in validation_results:
            if not is_valid:
                continue

            geocode_result = gmaps.geocode(corrected_name, components={'country': country})
            if not geocode_result:
                continue

            location = geocode_result[0]['geometry']['location']
            address = geocode_result[0]['formatted_address']

            locations_info.append({
                "address": address,
                "latitude": location['lat'],
                "longitude": location['lng'],
                "corrected_name": corrected_name
            })

        if not locations_info:
            raise HTTPException(status_code=400, detail=f"None of the provided locations were valid Brazilian locations.")

        return locations_info
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting location details: {str(e)}")