import os
from typing import Tuple, Dict, Optional
from openai import OpenAI
import googlemaps
from fastapi import HTTPException

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
gmaps = googlemaps.Client(key=os.getenv("GOOGLEMAPS_API_KEY"))

SYSTEM_PROMPT = """Você é um sistema responsável por validar e corrigir nomes de regiões e localidades brasileiras da Amazonia legal.
Seu objetivo é analisar se o usuário digitou o nome correto e completo de uma região, considerando critérios oficiais e possíveis variações.

Critérios de Validação:
    1. Nomes Oficiais: Baseie-se nos nomes oficiais definidos pelo IBGE ou outras instituições relevantes.
    2. Abreviações Comuns: Aceite abreviações amplamente reconhecidas, mas prefira corrigir para o nome completo.
    3. Sinônimos: Considere nomes alternativos ou sinônimos reconhecidos para a mesma localidade ou região.
    4. Erros de Digitação: Identifique e sugira correções para erros ortográficos ou variações de escrita.
    5. Menor Nível Geográfico: A menor unidade válida é um município.

Formato de Saída:
    • T;<Nome Corrigido>;<Classificação> para entradas válidas.
    • F;<Nome Corrigido>;<Classificação> para entradas inválidas ou não reconhecidas."""

async def validate_brazilian_location(location_text: str) -> Tuple[bool, str, str]:
    """Validates if the input is a valid Brazilian city or region name."""
    try:
        completion = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": location_text}
            ]
        )
        response = completion.choices[0].message.content
        is_valid, corrected_name, region_type = response.split(";", 2)
        return (True, corrected_name.strip(), region_type.strip()) if is_valid.strip() == "T" else (False, location_text, 'inexistente')
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error validating location: {str(e)}")

async def get_location_details(location_text: str, country: str = "BR") -> Dict:
    """Gets location details including coordinates using Google Maps API."""
    try:
        is_valid, corrected_name, _ = await validate_brazilian_location(location_text)
        if not is_valid:
            raise HTTPException(status_code=400, detail=f"'{location_text}' is not a valid Brazilian location.")
        
        geocode_result = gmaps.geocode(corrected_name, components={'country': country})
        if not geocode_result:
            raise HTTPException(status_code=404, detail="Location not found in Google Maps")
        
        location = geocode_result[0]['geometry']['location']
        address = geocode_result[0]['formatted_address']
        
        return {
            "address": address,
            "latitude": location['lat'],
            "longitude": location['lng'],
            "corrected_name": corrected_name
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting location details: {str(e)}")
