import streamlit as st
import requests
import re
import time
import json
from datetime import datetime
import sqlite3
import hashlib
from typing import List, Dict, Optional, Tuple
import uuid

# Set up the Streamlit app
st.set_page_config(page_title="CineAI - AI Movie Production Agent", page_icon="🎬", layout="wide")
st.title("🎬 CineAI - AI Movie Production Agent")
st.caption("Bring your movie ideas to life with AI-powered script writing and casting")

# Modern CSS styling
st.markdown("""
<style>
    :root {
        --primary: #ff4b4b;
        --secondary: #1f77b4;
        --success: #28a745;
        --warning: #ffc107;
        --dark: #2c3e50;
        --light: #f8f9fa;
    }
    
    .main-container {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 20px;
        border-radius: 15px;
        margin-bottom: 20px;
    }
    
    .card {
        background: white;
        padding: 25px;
        border-radius: 15px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.1);
        margin: 15px 0;
        border: 1px solid #e9ecef;
    }
    
    .industry-tag {
        display: inline-block;
        padding: 6px 16px;
        border-radius: 25px;
        font-size: 0.85em;
        font-weight: 600;
        margin: 4px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    .hollywood {
        background: linear-gradient(45deg, #ff4b4b, #ff6b6b);
        color: white;
    }
    
    .bollywood {
        background: linear-gradient(45deg, #ffd700, #ffed4e);
        color: #2c3e50;
    }
    
    .actor-card {
        background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
        padding: 20px;
        border-radius: 12px;
        margin: 12px 0;
        border-left: 4px solid var(--primary);
    }
    
    .stat-container {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 15px;
        margin: 20px 0;
    }
    
    .stat-card {
        background: white;
        padding: 20px;
        border-radius: 12px;
        text-align: center;
        box-shadow: 0 5px 15px rgba(0,0,0,0.08);
    }
    
    .stat-number {
        font-size: 2.5em;
        font-weight: bold;
        color: var(--primary);
        margin: 0;
    }
    
    .stat-label {
        color: var(--dark);
        font-size: 0.9em;
        opacity: 0.8;
    }
</style>
""", unsafe_allow_html=True)

# Database setup
def init_db():
    conn = sqlite3.connect('movie_agent.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            gemini_api_key TEXT,
            serp_api_key TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS movie_concepts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT,
            industry TEXT,
            concept_data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# Password hashing
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# User authentication functions
def create_user(username, password):
    conn = sqlite3.connect('movie_agent.db')
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, hash_password(password))
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def authenticate_user(username, password):
    conn = sqlite3.connect('movie_agent.db')
    c = conn.cursor()
    c.execute(
        "SELECT id, password_hash FROM users WHERE username = ?",
        (username,)
    )
    user = c.fetchone()
    conn.close()
    
    if user and user[1] == hash_password(password):
        return user[0]
    return None

def get_user_api_keys(user_id):
    conn = sqlite3.connect('movie_agent.db')
    c = conn.cursor()
    c.execute(
        "SELECT gemini_api_key, serp_api_key FROM users WHERE id = ?",
        (user_id,)
    )
    keys = c.fetchone()
    conn.close()
    return keys or (None, None)

def save_user_api_keys(user_id, gemini_key, serp_key):
    conn = sqlite3.connect('movie_agent.db')
    c = conn.cursor()
    c.execute(
        "UPDATE users SET gemini_api_key = ?, serp_api_key = ? WHERE id = ?",
        (gemini_key, serp_key, user_id)
    )
    conn.commit()
    conn.close()

def save_movie_concept(user_id, title, industry, concept_data):
    conn = sqlite3.connect('movie_agent.db')
    c = conn.cursor()
    c.execute(
        "INSERT INTO movie_concepts (user_id, title, industry, concept_data) VALUES (?, ?, ?, ?)",
        (user_id, title, industry, json.dumps(concept_data))
    )
    conn.commit()
    conn.close()

def get_user_concepts(user_id):
    conn = sqlite3.connect('movie_agent.db')
    c = conn.cursor()
    c.execute(
        "SELECT id, title, industry, created_at FROM movie_concepts WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,)
    )
    concepts = c.fetchall()
    conn.close()
    return concepts

def get_concept_details(concept_id):
    conn = sqlite3.connect('movie_agent.db')
    c = conn.cursor()
    c.execute(
        "SELECT concept_data FROM movie_concepts WHERE id = ?",
        (concept_id,)
    )
    concept = c.fetchone()
    conn.close()
    return json.loads(concept[0]) if concept else None

# Initialize session state
if 'user_id' not in st.session_state:
    st.session_state.user_id = None
if 'username' not in st.session_state:
    st.session_state.username = None
if 'concept_data' not in st.session_state:
    st.session_state.concept_data = None
if 'page' not in st.session_state:
    st.session_state.page = 'login'
if 'industry_trends' not in st.session_state:
    st.session_state.industry_trends = {}

# Improved Gemini API call
def call_gemini_api(api_key: str, prompt: str) -> Optional[str]:
    try:
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
        headers = {
            'Content-Type': 'application/json',
            'X-goog-api-key': api_key
        }
        data = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.8,
                "topK": 40,
                "topP": 0.95,
                "maxOutputTokens": 4096
            }
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=60)
        response.raise_for_status()
        
        result = response.json()
        if result.get('candidates') and result['candidates'][0].get('content'):
            return result['candidates'][0]['content']['parts'][0]['text']
        
        return None
        
    except Exception as e:
        st.error(f"❌ Gemini API Error: {str(e)}")
        return None

# Improved actor name extraction
def extract_actor_names(text: str) -> List[str]:
    patterns = [
        r'\b([A-Z][a-z]+ [A-Z][a-z]+)\b',
        r'[-•*]\s+([A-Z][a-z]+ [A-Z][a-z]+)',
        r'\*\*([A-Z][a-z]+ [A-Z][a-z]+)\*\*',
        r'([A-Z][a-z]+ [A-Z][a-z]+)(?=\s*[:,-])'
    ]
    
    actors = set()
    for pattern in patterns:
        found_actors = re.findall(pattern, text)
        actors.update(found_actors)
    
    false_positives = {'Diversity Considerations', 'Potential Chemistry', 'Current Availability', 
                      'Box Office', 'Market Research', 'Social Media', 'Recent Projects'}
    actors = [actor for actor in actors if actor not in false_positives and len(actor.split()) >= 2]
    
    return list(actors)[:6]

# Real actor research with SerpAPI
def search_actor_info(actor_name: str, api_key: str, industry: str) -> Dict:
    try:
        if industry == "Bollywood":
            search_query = f"{actor_name} Bollywood actor latest movies 2024 new projects filmography"
        else:
            search_query = f"{actor_name} Hollywood actor latest movies 2024 new projects filmography"
        
        params = {
            'q': search_query,
            'api_key': api_key,
            'engine': 'google',
            'num': 8
        }
        
        response = requests.get('https://serpapi.com/search', params=params, timeout=20)
        response.raise_for_status()
        data = response.json()
        
        actor_info = {
            'name': actor_name,
            'latest_projects': [],
            'news': [],
            'status': 'Active'
        }
        
        # Process organic results
        organic_results = data.get('organic_results', [])
        for result in organic_results[:5]:
            if any(keyword in result.get('title', '').lower() for keyword in ['movie', 'film', 'series', 'project']):
                actor_info['latest_projects'].append({
                    'title': result.get('title', ''),
                    'description': result.get('snippet', ''),
                    'link': result.get('link', '')
                })
        
        # Process news results if available
        news_results = data.get('news_results', [])
        for news in news_results[:3]:
            actor_info['news'].append({
                'title': news.get('title', ''),
                'summary': news.get('snippet', ''),
                'source': news.get('source', ''),
                'date': news.get('date', ''),
                'link': news.get('link', '')
            })
        
        return actor_info
        
    except Exception as e:
        return {'name': actor_name, 'error': f"Research failed: {str(e)}"}

# Real industry trends research
def get_industry_trends(api_key: str, industry: str) -> Dict:
    try:
        if industry == "Bollywood":
            search_query = "Bollywood 2024 box office hits trends new movies Indian cinema industry news"
        else:
            search_query = "Hollywood 2024 box office hits trends new movies industry news"
        
        params = {
            'q': search_query,
            'api_key': api_key,
            'engine': 'google',
            'num': 10,
            'tbm': 'nws'
        }
        
        response = requests.get('https://serpapi.com/search', params=params, timeout=20)
        response.raise_for_status()
        data = response.json()
        
        trends = {
            'latest_news': [],
            'market_trends': [],
            'successful_films': []
        }
        
        # Process news results
        news_results = data.get('news_results', [])
        for news in news_results[:6]:
            trends['latest_news'].append({
                'title': news.get('title', ''),
                'summary': news.get('snippet', ''),
                'source': news.get('source', ''),
                'date': news.get('date', ''),
                'link': news.get('link', '')
            })
        
        return trends
        
    except Exception as e:
        return {'error': f"Trends research failed: {str(e)}"}

# Authentication Pages
def login_page():
    st.markdown("""
    <div style='max-width: 400px; margin: 0 auto; padding: 20px;'>
        <h2 style='text-align: center; color: #ff4b4b;'>User Authentication!</h2>
    </div>
    """, unsafe_allow_html=True)
    
    tab1, tab2 = st.tabs(["Login", "Register"])
    
    with tab1:
        username = st.text_input("Username", key="login_username")
        password = st.text_input("Password", type="password", key="login_password")
        if st.button("Login", use_container_width=True):
            user_id = authenticate_user(username, password)
            if user_id:
                st.session_state.user_id = user_id
                st.session_state.username = username
                st.session_state.page = 'main'
                st.rerun()
            else:
                st.error("Invalid username or password")
    
    with tab2:
        new_username = st.text_input("Username", key="reg_username")
        new_password = st.text_input("Password", type="password", key="reg_password")
        confirm_password = st.text_input("Confirm Password", type="password", key="reg_confirm")
        
        if st.button("Create Account", use_container_width=True):
            if new_password != confirm_password:
                st.error("Passwords do not match")
            elif len(new_password) < 6:
                st.error("Password must be at least 6 characters")
            else:
                if create_user(new_username, new_password):
                    st.success("Account created successfully! Please login.")
                else:
                    st.error("Username already exists")

# Main application
def main_app():
    with st.sidebar:
        st.header(f"👋 Welcome, {st.session_state.username}!")
        
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.user_id = None
            st.session_state.username = None
            st.session_state.page = 'login'
            st.session_state.concept_data = None
            st.rerun()
        
        st.markdown("---")
        page_option = st.radio("Navigate to:", 
                              ["Create New Concept", "My Saved Concepts", "API Settings"])
        
        if page_option == "API Settings":
            st.session_state.page = 'settings'
        elif page_option == "My Saved Concepts":
            st.session_state.page = 'saved'
        else:
            st.session_state.page = 'main'
    
    gemini_api_key, serp_api_key = get_user_api_keys(st.session_state.user_id)
    
    if st.session_state.page == 'main':
        show_main_content(gemini_api_key, serp_api_key)
    elif st.session_state.page == 'settings':
        show_settings_page()
    elif st.session_state.page == 'saved':
        show_saved_concepts()

def show_settings_page():
    st.header("⚙️ API Settings")
    gemini_api_key, serp_api_key = get_user_api_keys(st.session_state.user_id)
    
    with st.form("api_settings_form"):
        new_gemini_key = st.text_input("Google Gemini API Key", 
                                      value=gemini_api_key or "", 
                                      type="password")
        new_serp_key = st.text_input("SerpAPI Key (optional)", 
                                    value=serp_api_key or "", 
                                    type="password")
        
        if st.form_submit_button("💾 Save API Keys", use_container_width=True):
            save_user_api_keys(st.session_state.user_id, new_gemini_key, new_serp_key)
            st.success("API keys saved successfully!")

def show_saved_concepts():
    st.header("📚 My Saved Concepts")
    concepts = get_user_concepts(st.session_state.user_id)
    
    if not concepts:
        st.info("You haven't saved any movie concepts yet.")
        return
    
    for concept_id, title, industry, created_at in concepts:
        # FIXED: Remove unsafe_allow_html parameter from expander
        with st.expander(f"{title} - {industry} - {created_at.split()[0]}"):
            industry_class = "hollywood" if industry == "Hollywood" else "bollywood"
            st.markdown(f"<span class='industry-tag {industry_class}'>{industry}</span>", unsafe_allow_html=True)
            st.write(f"Created: {created_at}")
            
            if st.button("Load Concept", key=f"load_{concept_id}"):
                concept_data = get_concept_details(concept_id)
                if concept_data:
                    st.session_state.concept_data = concept_data
                    st.rerun()

def show_main_content(gemini_api_key, serp_api_key):
    st.header("🎬 Create Movie Concept")
    
    if not gemini_api_key:
        st.error("⚠️ Please set your Gemini API key in Settings to generate concepts")
        return
    
    industry = st.radio("Select Industry:", ["Hollywood", "Bollywood"], horizontal=True)
    
    # Real-time trends
    if serp_api_key:
        with st.expander("📈 Live Industry Trends", expanded=True):
            if industry not in st.session_state.industry_trends:
                with st.spinner("🔄 Fetching real-time trends..."):
                    trends_data = get_industry_trends(serp_api_key, industry)
                    st.session_state.industry_trends[industry] = trends_data
            
            trends = st.session_state.industry_trends[industry]
            if 'error' in trends:
                st.error(trends['error'])
            else:
                for news in trends.get('latest_news', [])[:3]:
                    st.markdown(f"**{news['title']}**")
                    st.caption(f"{news['source']} - {news.get('date', 'Recent')}")
                    st.write(news['summary'])
                    st.markdown("---")
    
    # Concept input
    movie_idea = st.text_area("Movie Idea:", height=100,
                             placeholder="Describe your movie concept...")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        genre = st.selectbox("Genre", ["Action", "Comedy", "Drama", "Sci-Fi", "Horror", "Romance", "Thriller"])
    with col2:
        target_audience = st.selectbox("Audience", ["General", "Teenagers", "Adults", "Family"])
    with col3:
        runtime = st.slider("Runtime (min)", 60, 180, 120)
    
    concept_title = st.text_input("Concept Title", "My Movie Concept")
    
    if st.button("🚀 Generate Complete Concept", use_container_width=True):
        if not movie_idea:
            st.error("Please enter a movie idea")
            return
            
        with st.spinner("Creating your movie concept... This may take 2-3 minutes"):
            # Generate script
            script_prompt = f"""Create a detailed script outline for a {industry} {genre} movie:

Title: {concept_title}
Industry: {industry}
Genre: {genre}
Audience: {target_audience}
Runtime: {runtime} minutes
Idea: {movie_idea}

Include: 3-act structure, character descriptions, key plot points, and twists."""
            
            script_output = call_gemini_api(gemini_api_key, script_prompt)
            if not script_output:
                return
                
            # Generate casting
            casting_prompt = f"""Suggest casting for this {industry} movie:

{script_output}

For each main character, suggest 2-3 {industry} actors with reasons. Consider availability and suitability."""
            
            casting_output = call_gemini_api(gemini_api_key, casting_prompt)
            if not casting_output:
                return
                
            # Generate production notes
            production_prompt = f"""Create production notes for this {industry} movie:

Script: {script_output[:1000]}
Casting: {casting_output[:1000]}

Include: budget estimate, filming locations, director suggestions, marketing strategy."""
            
            production_output = call_gemini_api(gemini_api_key, production_prompt)
            if not production_output:
                return
                
            # Save concept
            concept_data = {
                'script': script_output,
                'casting': casting_output,
                'production': production_output,
                'timestamp': datetime.now().isoformat()
            }
            
            st.session_state.concept_data = concept_data
            save_movie_concept(st.session_state.user_id, concept_title, industry, concept_data)
            st.success("Concept generated successfully!")
    
    # Display results
    if st.session_state.concept_data:
        data = st.session_state.concept_data
        
        st.markdown("---")
        st.subheader("📜 Script Outline")
        st.write(data['script'])
        
        st.subheader("🎭 Casting Suggestions")
        st.write(data['casting'])
        
        # Real actor research
        if serp_api_key:
            st.subheader("🔍 Actor Research")
            actors = extract_actor_names(data['casting'])
            if actors:
                for actor in actors:
                    with st.expander(f"🎬 {actor}"):
                        actor_info = search_actor_info(actor, serp_api_key, industry)
                        if 'error' in actor_info:
                            st.error(actor_info['error'])
                        else:
                            if actor_info['latest_projects']:
                                st.write("**Latest Projects:**")
                                for project in actor_info['latest_projects'][:3]:
                                    st.write(f"- {project['title']}")
                                    if project['description']:
                                        st.caption(project['description'])
                            if actor_info['news']:
                                st.write("**Recent News:**")
                                for news in actor_info['news'][:2]:
                                    st.write(f"- {news['title']}")
                                    st.caption(f"{news['source']} - {news.get('date', 'Recent')}")
        
        st.subheader("💼 Production Notes")
        st.write(data['production'])
        
        # Download
        concept_text = f"""MOVIE CONCEPT: {concept_title}
Industry: {industry}
Generated: {data['timestamp']}

SCRIPT:
{data['script']}

CASTING:
{data['casting']}

PRODUCTION:
{data['production']}"""
        
        st.download_button("📥 Download Concept", concept_text, 
                          file_name=f"{concept_title.replace(' ', '_')}.txt")

# Run the app
if __name__ == "__main__":
    if st.session_state.user_id is None:
        login_page()
    else:
        main_app()