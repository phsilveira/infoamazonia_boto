#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import random
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from models import User, UserInteraction
from database import SessionLocal, engine, Base

# List of Portuguese content about Amazon for different categories
amazon_articles = [
    "A Floresta Amazônica e sua biodiversidade única",
    "Desmatamento na Amazônia atinge níveis alarmantes em 2023",
    "Povos indígenas da Amazônia lutam para preservar suas terras",
    "Novos estudos revelam espécies desconhecidas na Amazônia",
    "O impacto das mudanças climáticas na floresta amazônica",
    "Amazônia: o pulmão do mundo em perigo",
    "A importância da Amazônia para o equilíbrio climático global",
    "Projetos de conservação na Amazônia mostram resultados positivos",
    "A economia sustentável como alternativa para a Amazônia",
    "Rios da Amazônia: as artérias da maior floresta tropical do mundo",
    "A medicina tradicional dos povos da Amazônia",
    "Expedição científica descobre novas plantas medicinais na Amazônia",
    "A fauna ameaçada de extinção na Amazônia",
    "O ciclo hidrológico e o papel da Amazônia",
    "Amazônia Azul: a biodiversidade marinha da costa amazônica",
    "A culinária amazônica e seus ingredientes exóticos",
    "Turismo sustentável na região amazônica",
    "A luta contra o garimpo ilegal na Amazônia",
    "Tecnologias de monitoramento para proteger a Amazônia",
    "O Acordo de Paris e as metas para a preservação da Amazônia",
    "Amazônia: berço de civilizações antigas ainda pouco estudadas",
    "As lendas e mitos dos povos amazônicos",
    "Ameaças à biodiversidade da Amazônia: um alerta global",
    "Pesquisadores catalogam novas espécies de pássaros na Amazônia",
    "A importância dos corredores ecológicos na Amazônia",
    "Agricultura sustentável como solução para o desmatamento na Amazônia",
    "O papel das ONGs na proteção da floresta amazônica",
    "Amazônia: fonte de inspiração para artistas brasileiros",
    "O debate sobre a internacionalização da Amazônia",
    "Políticas públicas para conservação da Amazônia",
    "Amazônia Legal: aspectos jurídicos e ambientais",
    "Mudanças no código florestal e seus impactos na Amazônia",
    "A fotossíntese na Amazônia e sua importância para o planeta",
    "Festival de Parintins: manifestação cultural da Amazônia",
    "O tráfico de animais silvestres na região amazônica",
    "Anfíbios amazônicos e sua importância ecológica",
    "O rio Amazonas: características e importância",
    "As queimadas na Amazônia e suas consequências",
    "Economia circular: alternativas para o desenvolvimento sustentável na Amazônia",
    "A pesca sustentável nos rios amazônicos",
    "A Amazônia e seu potencial para o ecoturismo",
    "Plantas carnívoras da Amazônia: raridades botânicas",
    "Desafios na proteção das fronteiras da Amazônia",
    "Borracha: o ciclo econômico que transformou a Amazônia",
    "Amazônia: laboratório natural para estudos sobre evolução",
    "Construção de hidroelétricas na Amazônia: impactos ambientais",
    "Arqueologia na Amazônia revela sociedades complexas pré-colombianas",
    "A influência da floresta amazônica no regime de chuvas da América do Sul",
    "Anfíbios da Amazônia: indicadores da saúde ambiental",
    "O Projeto REDD+ e seus resultados na Amazônia brasileira"
]

amazon_terms = [
    "O que é o Tratado de Cooperação Amazônica?",
    "Como funciona o ciclo hidrológico na Amazônia?",
    "Qual a diferença entre Amazônia Legal e Floresta Amazônica?",
    "O que significa biodiversidade na Amazônia?",
    "Como identificar madeira de origem legal da Amazônia?",
    "O que são terras indígenas demarcadas na Amazônia?",
    "Qual a importância das áreas de preservação na Amazônia?",
    "O que é biopirataria na Amazônia?",
    "O que são os rios de água preta da Amazônia?",
    "Como funciona o sistema de várzea na Amazônia?",
    "O que é o fenômeno da piracema nos rios amazônicos?",
    "O que são igapós na Amazônia?",
    "Quais são os principais povos indígenas da Amazônia?",
    "O que é o Sistema de Alerta de Desmatamento da Amazônia?",
    "O que significa desenvolvimento sustentável para a Amazônia?",
    "Como funcionam as reservas extrativistas na Amazônia?",
    "O que é o Fundo Amazônia?",
    "Qual a diferença entre desmatamento e degradação florestal?",
    "O que são hotspots de biodiversidade na Amazônia?",
    "Como funciona o sequestro de carbono na floresta amazônica?",
    "O que é o fenômeno da terra preta na Amazônia?",
    "Quais são os serviços ecossistêmicos da Amazônia?",
    "O que são corredores ecológicos na Amazônia?",
    "Como os povos tradicionais usam plantas medicinais na Amazônia?",
    "O que é manejo florestal sustentável na Amazônia?",
    "O que é o programa de monitoramento por satélite PRODES?",
    "Como funciona a economia da floresta em pé?",
    "O que é o bioma amazônico?",
    "Qual a relação entre a Amazônia e o clima global?",
    "O que são unidades de conservação na Amazônia?",
    "Como funciona o sistema agroflorestal na Amazônia?",
    "O que é o fenômeno das terras caídas nos rios amazônicos?",
    "O que é o Programa Áreas Protegidas da Amazônia (ARPA)?",
    "Como funcionam as florestas nacionais na Amazônia?",
    "O que são quelônios amazônicos e por que estão ameaçados?",
    "Como a legislação protege as nascentes dos rios amazônicos?",
    "O que é o movimento dos seringueiros na Amazônia?",
    "Qual a importância das abelhas nativas para a Amazônia?",
    "O que são castanhais na Amazônia?",
    "Como funciona o ciclo do carbono na floresta amazônica?",
    "O que é o Projeto de Monitoramento da Amazônia por Satélite?",
    "O que são terras devolutas na Amazônia?",
    "Como funciona a dispersão de sementes na floresta amazônica?",
    "O que é o fenômeno da friagem na Amazônia?",
    "Quais são os principais produtos do extrativismo amazônico?",
    "Como funciona a cadeia produtiva da castanha-do-brasil?",
    "O que são peixes ornamentais amazônicos?",
    "Como a urbanização afeta a Amazônia?",
    "O que é o conceito de floresta cultural na Amazônia?",
    "Qual a importância dos quelônios para o ecossistema amazônico?"
]

amazon_news_suggestions = [
    "Gostaria de receber notícias sobre conservação da biodiversidade na Amazônia",
    "Tenho interesse em notícias sobre projetos sustentáveis na região amazônica",
    "Quero receber informações sobre as comunidades indígenas da Amazônia",
    "Gostaria de acompanhar notícias sobre descobertas científicas na Amazônia",
    "Tenho interesse em notícias sobre políticas de preservação da floresta amazônica",
    "Quero receber atualizações sobre o combate ao desmatamento na Amazônia",
    "Gostaria de acompanhar notícias sobre expedições científicas na Amazônia",
    "Tenho interesse em notícias sobre fauna e flora amazônicas",
    "Quero receber informações sobre economia sustentável na Amazônia",
    "Gostaria de acompanhar notícias sobre o impacto das mudanças climáticas na Amazônia",
    "Tenho interesse em notícias sobre medicina tradicional amazônica",
    "Quero receber atualizações sobre turismo ecológico na Amazônia",
    "Gostaria de acompanhar notícias sobre arqueologia na região amazônica",
    "Tenho interesse em notícias sobre culinária amazônica",
    "Quero receber informações sobre os rios e peixes da Amazônia",
    "Gostaria de acompanhar notícias sobre o Fundo Amazônia",
    "Tenho interesse em notícias sobre legislação ambiental para a Amazônia",
    "Quero receber atualizações sobre as reservas extrativistas na Amazônia",
    "Gostaria de acompanhar notícias sobre os guardiões da floresta",
    "Tenho interesse em notícias sobre artesanato amazônico",
    "Quero receber informações sobre festivais culturais da Amazônia",
    "Gostaria de acompanhar notícias sobre pesquisas de plantas medicinais amazônicas",
    "Tenho interesse em notícias sobre conservação de espécies ameaçadas na Amazônia",
    "Quero receber atualizações sobre tecnologias para monitoramento da floresta",
    "Gostaria de acompanhar notícias sobre as estações do ano na Amazônia",
    "Tenho interesse em notícias sobre a qualidade da água nos rios amazônicos",
    "Quero receber informações sobre as frutas exóticas da Amazônia",
    "Gostaria de acompanhar notícias sobre a Zona Franca de Manaus",
    "Tenho interesse em notícias sobre os projetos de reflorestamento na Amazônia",
    "Quero receber atualizações sobre os quelônios amazônicos",
    "Gostaria de acompanhar notícias sobre a pesca sustentável na Amazônia",
    "Tenho interesse em notícias sobre as mulheres das comunidades ribeirinhas",
    "Quero receber informações sobre a música e dança tradicionais da Amazônia",
    "Gostaria de acompanhar notícias sobre acordos internacionais para proteção da Amazônia",
    "Tenho interesse em notícias sobre as reservas biológicas na Amazônia",
    "Quero receber atualizações sobre as unidades de conservação na Amazônia",
    "Gostaria de acompanhar notícias sobre os saberes tradicionais dos povos amazônicos",
    "Tenho interesse em notícias sobre o ecoturismo na região amazônica",
    "Quero receber informações sobre as áreas protegidas na Amazônia",
    "Gostaria de acompanhar notícias sobre o extrativismo sustentável na Amazônia",
    "Tenho interesse em notícias sobre o combate à biopirataria na Amazônia",
    "Quero receber atualizações sobre os ciclos naturais da floresta amazônica",
    "Gostaria de acompanhar notícias sobre fotografias e documentários da Amazônia",
    "Tenho interesse em notícias sobre cidades sustentáveis na Amazônia",
    "Quero receber informações sobre os botos e golfinhos dos rios amazônicos",
    "Gostaria de acompanhar notícias sobre os anfíbios da Amazônia",
    "Tenho interesse em notícias sobre as lendas e mitos da floresta amazônica",
    "Quero receber atualizações sobre as pesquisas genéticas com espécies amazônicas",
    "Gostaria de acompanhar notícias sobre as ilhas fluviais do Amazonas",
    "Tenho interesse em notícias sobre as tribos isoladas da Amazônia"
]

# Sample responses for each category
article_responses = [
    "Aqui está um artigo sobre este tema: {}. Espero que seja útil para você.",
    "Encontrei um artigo relevante sobre: {}. Confira o link para ler mais.",
    "Recomendo este artigo sobre: {}. Tem informações importantes sobre o assunto.",
    "Este artigo pode interessar você: {}. É um bom ponto de partida para entender o tema.",
    "Separei um artigo interessante sobre: {}. Veja se atende suas necessidades."
]

term_responses = [
    "{} refere-se a um conceito importante na ecologia amazônica. Resumidamente, {}.",
    "Sobre {}, posso explicar que é {}. Espero ter esclarecido sua dúvida.",
    "{} é um termo que significa {}. É um conceito fundamental para entender a região amazônica.",
    "A definição de {} é {}. Este conhecimento é importante para compreender a dinâmica da Amazônia.",
    "Em relação a {}, posso informar que {}. É um tema relevante para a preservação da floresta."
]

news_suggestion_responses = [
    "Sua solicitação para receber notícias sobre {} foi registrada com sucesso. Você receberá atualizações regularmente.",
    "Obrigado pelo seu interesse em {}. Adicionamos este tópico às suas preferências de notícias.",
    "Registramos seu interesse em receber informações sobre {}. Você receberá notícias sobre este tema.",
    "Sua inscrição para notícias sobre {} foi confirmada. Manteremos você atualizado sobre este assunto.",
    "Agradecemos seu interesse em {}. A partir de agora, você receberá notícias relacionadas a este tema."
]

# Phone number generation
def generate_phone_number():
    # Brazilian phone number format: +55 (XX) 9XXXX-XXXX
    ddd = random.randint(11, 99)
    number = random.randint(10000000, 99999999)
    return f"+55{ddd}9{number}"

# Date generation within the last year
def random_date():
    days_back = random.randint(0, 365)
    return datetime.utcnow() - timedelta(days=days_back)

def insert_fake_data():
    db = SessionLocal()
    try:
        # Check if users exist
        existing_users = db.query(User).all()
        
        # Create users if none exist
        users = []
        if not existing_users:
            print("Creating fake users...")
            for i in range(10):
                phone_number = generate_phone_number()
                schedule_options = ["daily", "weekly", "monthly", "immediately"]
                user = User(
                    phone_number=phone_number,
                    name=f"Usuário {i+1}",
                    is_active=True,
                    schedule=random.choice(schedule_options),
                    created_at=random_date()
                )
                db.add(user)
            db.commit()
            users = db.query(User).all()
        else:
            users = existing_users
        
        # Create user interactions
        print("Creating fake user interactions...")
        
        # Article interactions
        for i in range(50):
            user = random.choice(users)
            article = random.choice(amazon_articles)
            response = random.choice(article_responses).format(article)
            
            interaction = UserInteraction(
                user_id=user.id,
                phone_number=user.phone_number,
                category="article",
                query=f"Procuro artigos sobre {article.lower()}",
                response=response,
                feedback=random.choice([True, False, None]),
                created_at=random_date(),
                updated_at=random_date()
            )
            db.add(interaction)
        
        # Terms interactions
        for i in range(50):
            user = random.choice(users)
            term = random.choice(amazon_terms)
            term_explanation = f"um conceito relacionado à {random.choice(['biodiversidade', 'preservação', 'cultura indígena', 'ecologia', 'hidrografia', 'fauna', 'flora', 'sustentabilidade'])} da Amazônia"
            response = random.choice(term_responses).format(term, term_explanation)
            
            interaction = UserInteraction(
                user_id=user.id,
                phone_number=user.phone_number,
                category="term",
                query=term,
                response=response,
                feedback=random.choice([True, False, None]),
                created_at=random_date(),
                updated_at=random_date()
            )
            db.add(interaction)
        
        # News suggestion interactions
        for i in range(50):
            user = random.choice(users)
            suggestion = random.choice(amazon_news_suggestions)
            topic = suggestion.split("sobre ")[-1].split("na Amazônia")[0].strip()
            if not topic:
                topic = "a Amazônia"
            response = random.choice(news_suggestion_responses).format(topic)
            
            interaction = UserInteraction(
                user_id=user.id,
                phone_number=user.phone_number,
                category="news_suggestion",
                query=suggestion,
                response=response,
                feedback=random.choice([True, False, None]),
                created_at=random_date(),
                updated_at=random_date()
            )
            db.add(interaction)
        
        db.commit()
        print("Fake data insertion completed successfully!")
        print(f"Added 50 article interactions, 50 term interactions, and 50 news suggestion interactions")
        
    except Exception as e:
        db.rollback()
        print(f"Error inserting fake data: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    insert_fake_data()