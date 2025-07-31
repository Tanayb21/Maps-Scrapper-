import streamlit as st
import time
import re
import csv
import pandas as pd
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import logging
import base64
from PIL import Image
import plotly.express as px
import plotly.graph_objects as go

# Configure logging to suppress unnecessary messages
logging.getLogger('selenium').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

class GoogleMapsExtractorStreamlit:
    def __init__(self, headless=True):
        """Initialize the Google Maps extractor with Chrome driver"""
        self.options = webdriver.ChromeOptions()
        if headless:
            self.options.add_argument('--headless')
        self.options.add_argument('--no-sandbox')
        self.options.add_argument('--disable-dev-shm-usage')
        self.options.add_argument('--disable-blink-features=AutomationControlled')
        self.options.add_experimental_option("excludeSwitches", ["enable-automation"])
        self.options.add_experimental_option('useAutomationExtension', False)
        self.options.add_argument('--log-level=3')
        self.options.add_experimental_option('excludeSwitches', ['enable-logging'])
        self.options.add_argument('--disable-gpu')
        self.options.add_argument('--window-size=1920,1080')
        
        self.driver = None
        self.wait = None
        self.results = []
        self.stop_extraction = False
        
    def initialize_driver(self):
        """Initialize the webdriver"""
        try:
            # Try multiple approaches to initialize Chrome driver
            try:
                # Method 1: Direct Chrome initialization
                self.driver = webdriver.Chrome(options=self.options)
            except Exception as e1:
                try:
                    # Method 2: Try with explicit executable path
                    from selenium.webdriver.chrome.service import Service
                    service = Service()
                    self.driver = webdriver.Chrome(service=service, options=self.options)
                except Exception as e2:
                    try:
                        # Method 3: Try with webdriver-manager if available
                        from webdriver_manager.chrome import ChromeDriverManager
                        from selenium.webdriver.chrome.service import Service
                        service = Service(ChromeDriverManager().install())
                        self.driver = webdriver.Chrome(service=service, options=self.options)
                    except ImportError:
                        return False, "ChromeDriver not found. Please install ChromeDriver or webdriver-manager"
                    except Exception as e3:
                        return False, f"All driver initialization methods failed. Last error: {str(e3)}"
            
            self.wait = WebDriverWait(self.driver, 10)
            return True, "Driver initialized successfully"
            
        except Exception as e:
            return False, f"Failed to initialize Chrome driver: {str(e)}. Please ensure Chrome browser and ChromeDriver are installed."
    
    def search_google_maps(self, query):
        """Perform search on Google Maps"""
        try:
            if not self.driver:
                result = self.initialize_driver()
                if isinstance(result, tuple):
                    success, error = result
                    if not success:
                        return False, error
                else:
                    # Handle case where only boolean is returned
                    if not result:
                        return False, "Failed to initialize driver"
            
            # Navigate to Google Maps
            self.driver.get("https://www.google.com/maps")
            time.sleep(3)
            
            # Handle cookies/consent if present
            try:
                accept_buttons = self.driver.find_elements(By.XPATH, 
                    "//button[contains(text(), 'Accept') or contains(text(), 'Reject') or contains(text(), 'Got it')]")
                if accept_buttons:
                    accept_buttons[0].click()
                    time.sleep(1)
            except:
                pass
            
            # Find search box and perform search
            search_box = self.wait.until(
                EC.presence_of_element_located((By.ID, "searchboxinput"))
            )
            search_box.clear()
            search_box.send_keys(query)
            
            # Click search button
            search_button = self.driver.find_element(By.ID, "searchbox-searchbutton")
            search_button.click()
            
            # Wait for results to load
            self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'div[role="feed"]'))
            )
            time.sleep(3)
            
            return True, "Search successful"
            
        except Exception as e:
            return False, str(e)
    
    def extract_phone_from_text(self, text):
        """Extract phone numbers from text using regex"""
        if not text:
            return None
            
        text = text.strip()
        
        phone_patterns = [
            r'[\+]?[(]?[0-9]{1,3}[)]?[-\s\.]?[(]?[0-9]{1,4}[)]?[-\s\.]?[0-9]{1,4}[-\s\.]?[0-9]{1,9}',
            r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
            r'\b\d{10}\b'
        ]
        
        for pattern in phone_patterns:
            phones = re.findall(pattern, text)
            if phones:
                phone = phones[0].strip()
                if len(phone) >= 10:
                    return phone
        return None
    
    def extract_listing_details_from_panel(self):
        """Extract details from the currently open detail panel"""
        details = {
            'name': None,
            'phone': None,
            'email': None,
            'website': None,
            'address': None,
            'rating': None,
            'reviews_count': None,
            'category': None
        }
        
        try:
            time.sleep(2)
            
            # Extract name
            name_selectors = [
                'h1.DUwDvf.fontHeadlineLarge',
                'h1[class*="fontHeadlineLarge"]',
                'h1.DUwDvf',
                '[role="main"] h1'
            ]
            
            for selector in name_selectors:
                try:
                    name_element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if name_element and name_element.text:
                        details['name'] = name_element.text.strip()
                        break
                except:
                    continue
            
            # Extract category/type
            try:
                category_element = self.driver.find_element(By.CSS_SELECTOR, 
                    'button[jsaction*="category"] .DkEaL')
                details['category'] = category_element.text.strip()
            except:
                pass
            
            # Extract info from buttons
            info_buttons = self.driver.find_elements(By.CSS_SELECTOR, 
                'button[data-item-id], button[data-tooltip], a[data-item-id]')
            
            for button in info_buttons:
                try:
                    item_id = button.get_attribute('data-item-id') or ''
                    aria_label = button.get_attribute('aria-label') or ''
                    text = button.text or ''
                    
                    # Phone extraction
                    if 'phone' in item_id.lower() or 'phone' in aria_label.lower():
                        if aria_label and ':' in aria_label:
                            phone_text = aria_label.split(':', 1)[1].strip()
                            details['phone'] = phone_text
                        elif text:
                            phone = self.extract_phone_from_text(text)
                            if phone:
                                details['phone'] = phone
                    
                    # Website extraction
                    elif 'website' in item_id.lower() or 'website' in aria_label.lower():
                        if text and ('.' in text or 'http' in text.lower()):
                            details['website'] = text.strip()
                    
                    # Address extraction
                    elif 'address' in item_id.lower() or 'address' in aria_label.lower():
                        if aria_label and ':' in aria_label:
                            details['address'] = aria_label.split(':', 1)[1].strip()
                        elif text:
                            details['address'] = text.strip()
                            
                except:
                    continue
            
            # Try alternative selectors for missing data
            if not details['phone']:
                try:
                    phone_links = self.driver.find_elements(By.CSS_SELECTOR, 'a[href^="tel:"]')
                    if phone_links:
                        phone_href = phone_links[0].get_attribute('href')
                        details['phone'] = phone_href.replace('tel:', '').strip()
                except:
                    pass
            
            # Extract rating and reviews
            try:
                rating_element = self.driver.find_element(By.CSS_SELECTOR, 
                    'span[role="img"][aria-label*="stars"], span.MW4etd')
                rating_text = rating_element.get_attribute('aria-label') or rating_element.text
                if rating_text:
                    rating_match = re.search(r'([\d.]+)', rating_text)
                    if rating_match:
                        details['rating'] = rating_match.group(1)
            except:
                pass
            
            # Extract reviews count
            try:
                reviews_element = self.driver.find_element(By.CSS_SELECTOR, 
                    'span.UY7F9 button span[aria-label*="reviews"]')
                reviews_text = reviews_element.get_attribute('aria-label')
                if reviews_text:
                    reviews_match = re.search(r'([\d,]+)', reviews_text)
                    if reviews_match:
                        details['reviews_count'] = reviews_match.group(1)
            except:
                pass
            
            # Extract email
            try:
                panel = self.driver.find_element(By.CSS_SELECTOR, 'div[role="main"]')
                panel_text = panel.text
                email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
                emails = re.findall(email_pattern, panel_text)
                if emails:
                    details['email'] = emails[0]
            except:
                pass
            
        except Exception as e:
            pass
        
        return details
    
    def click_listing_by_index(self, index):
        """Click on a specific listing by index"""
        try:
            results_panel = self.driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')
            listings = results_panel.find_elements(By.CSS_SELECTOR, 'a[href*="/maps/place/"]')
            
            if index >= len(listings):
                return False
            
            listing = listings[index]
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", listing)
            time.sleep(1)
            self.driver.execute_script("arguments[0].click();", listing)
            time.sleep(2)
            
            return True
            
        except Exception as e:
            return False
    
    def get_total_results_count(self):
        """Get the total number of results currently loaded"""
        try:
            results_panel = self.driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')
            listings = results_panel.find_elements(By.CSS_SELECTOR, 'a[href*="/maps/place/"]')
            return len(listings)
        except:
            return 0
    
    def scroll_results_panel(self):
        """Scroll the results panel to load more results"""
        try:
            results_panel = self.driver.find_element(By.CSS_SELECTOR, 'div[role="feed"]')
            before_scroll = self.get_total_results_count()
            self.driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", results_panel)
            time.sleep(3)
            after_scroll = self.get_total_results_count()
            return after_scroll > before_scroll
        except:
            return False
    
    def extract_single_batch(self, max_results=50, progress_callback=None):
        """Extract a batch of results with real-time progress updates"""
        processed_indices = set()
        consecutive_failures = 0
        no_new_results_count = 0
        batch_results = []
        
        try:
            # Get initial results
            total_listings = self.get_total_results_count()
            while total_listings < max_results:
                 if not self.scroll_results_panel():
                    break
                 total_listings = self.get_total_results_count()
                
            if total_listings == 0:
                return batch_results, "No listings found"
            
            # Process listings
            for i in range(min(total_listings, max_results)):
                if self.stop_extraction:
                    break
                    
                if i in processed_indices:
                    continue
                
                # Update progress before processing
                if progress_callback:
                    progress_callback({
                        'stage': 'processing',
                        'current': i + 1,
                        'total': min(total_listings, max_results),
                        'extracted': len(batch_results),
                        'status': f"Processing listing {i + 1} of {min(total_listings, max_results)}..."
                    })
                
                try:
                    if self.click_listing_by_index(i):
                        # Show extracting status
                        if progress_callback:
                            progress_callback({
                                'stage': 'extracting',
                                'current': i + 1,
                                'total': min(total_listings, max_results),
                                'extracted': len(batch_results),
                                'status': "🔍 Extracting business details..."
                            })
                        
                        details = self.extract_listing_details_from_panel()
                        
                        if details['name']:
                            batch_results.append(details)
                            self.results.append(details)  # Store in instance for progress tracking
                            processed_indices.add(i)
                            consecutive_failures = 0
                            
                            # Show success with company name
                            if progress_callback:
                                progress_callback({
                                    'stage': 'success',
                                    'current': i + 1,
                                    'total': min(total_listings, max_results),
                                    'extracted': len(batch_results),
                                    'company_name': details['name'],
                                    'status': f"✅ Extracted: {details['name']}"
                                })
                        else:
                            consecutive_failures += 1
                            if progress_callback:
                                progress_callback({
                                    'stage': 'failed',
                                    'current': i + 1,
                                    'total': min(total_listings, max_results),
                                    'extracted': len(batch_results),
                                    'status': "⚠️ No data found for this listing"
                                })
                    else:
                        consecutive_failures += 1
                        if progress_callback:
                            progress_callback({
                                'stage': 'failed',
                                'current': i + 1,
                                'total': min(total_listings, max_results),
                                'extracted': len(batch_results),
                                'status': "❌ Failed to click listing"
                            })
                        
                except Exception as e:
                    consecutive_failures += 1
                    if progress_callback:
                        progress_callback({
                            'stage': 'error',
                            'current': i + 1,
                            'total': min(total_listings, max_results),
                            'extracted': len(batch_results),
                            'status': f"⚠️ Error: {str(e)[:50]}..."
                        })
                    
                    if "connection" in str(e).lower() or "session" in str(e).lower():
                        break
                
                # If too many failures, try scrolling
                if consecutive_failures > 3:
                    if progress_callback:
                        progress_callback({
                            'stage': 'scrolling',
                            'current': i + 1,
                            'total': min(total_listings, max_results),
                            'extracted': len(batch_results),
                            'status': "📜 Loading more results..."
                        })
                    
                    if not self.scroll_results_panel():
                        no_new_results_count += 1
                    else:
                        no_new_results_count = 0
                        total_listings = self.get_total_results_count()
                    consecutive_failures = 0
                
                if no_new_results_count > 2:
                    break
                    
                time.sleep(0.5)  # Small delay between extractions
                
        except Exception as e:
            return batch_results, f"Error during extraction: {str(e)}"
        
        # Final progress update
        if progress_callback:
            progress_callback({
                'stage': 'completed',
                'current': len(batch_results),
                'total': len(batch_results),
                'extracted': len(batch_results),
                'status': f"🎉 Extraction completed! Found {len(batch_results)} results"
            })
        
        return batch_results, "Success"
    
    def close(self):
        """Close the browser"""
        try:
            if self.driver:
                self.driver.quit()
        except:
            pass

def run_extraction_batch(extractor, query, max_results, progress_callback=None):
    """Run extraction in a separate function with progress updates"""
    try:
        if progress_callback:
            progress_callback({
                'stage': 'searching',
                'current': 0,
                'total': max_results,
                'extracted': 0,
                'status': "🔍 Searching Google Maps..."
            })
        
        success, message = extractor.search_google_maps(query)
        if not success:
            return [], f"Search failed: {message}"
        
        if progress_callback:
            progress_callback({
                'stage': 'found_results',
                'current': 0,
                'total': max_results,
                'extracted': 0,
                'status': "📋 Found search results, starting extraction..."
            })
        
        results, message = extractor.extract_single_batch(max_results, progress_callback)
        return results, message
        
    except Exception as e:
        return [], f"Extraction failed: {str(e)}"
    finally:
        extractor.close()

def create_analytics_charts(df):
    """Create analytics charts for the extracted data"""
    charts = {}
    
    if not df.empty:
        # Rating distribution
        if 'rating' in df.columns:
            rating_df = df[df['rating'].notna()].copy()
            if not rating_df.empty:
                rating_df['rating'] = pd.to_numeric(rating_df['rating'], errors='coerce')
                rating_df = rating_df[rating_df['rating'].notna()]
                
                if not rating_df.empty:
                    fig_rating = px.histogram(
                        rating_df, 
                        x='rating', 
                        nbins=10,
                        title="Business Rating Distribution",
                        color_discrete_sequence=['#2E86AB']
                    )
                    fig_rating.update_layout(
                        plot_bgcolor='rgba(0,0,0,0)',
                        paper_bgcolor='rgba(0,0,0,0)',
                        font=dict(color='black')
                    )
                    charts['rating'] = fig_rating
        
        # Category distribution
        if 'category' in df.columns:
            category_df = df[df['category'].notna()]
            if not category_df.empty:
                category_counts = category_df['category'].value_counts().head(10)
                fig_category = px.bar(
                    x=category_counts.values,
                    y=category_counts.index,
                    orientation='h',
                    title="Top Business Categories",
                    color=category_counts.values,
                    color_continuous_scale='Viridis'
                )
                fig_category.update_layout(
                    plot_bgcolor='rgba(0,0,0,0)',
                    paper_bgcolor='rgba(0,0,0,0)',
                    font=dict(color='white'),
                    yaxis={'categoryorder': 'total ascending'}
                )
                charts['category'] = fig_category
        
        # Contact information completeness
        contact_data = {
            'Phone': df['phone'].notna().sum(),
            'Email': df['email'].notna().sum(), 
            'Website': df['website'].notna().sum(),
            'Address': df['address'].notna().sum()
        }
        
        fig_contact = px.pie(
            values=list(contact_data.values()),
            names=list(contact_data.keys()),
            title="Contact Information Availability",
            color_discrete_sequence=['#A23B72', '#F18F01', '#C73E1D', '#2E86AB']
        )
        fig_contact.update_layout(
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(color='white')
        )
        charts['contact'] = fig_contact
    
    return charts

def load_custom_css():
    """Load custom CSS for styling"""
    st.markdown("""
    <style>
    /* Import Google Fonts */
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;600;700&display=swap');
    
    /* Main app styling */
    .main {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        font-family: 'Poppins', sans-serif;
    }
    
    /* Header styling */
    .header-container {
        background: linear-gradient(90deg, #f1f0ed 0%, #f1f0ed 100%);        border-radius: 15px;
        margin-bottom: 2rem;
        box-shadow: 0 10px 30px rgba(0,0,0,0.3);
        border: 1px solid rgba(255,255,255,0.1);
    }
    
    .company-title {
        color: #444 !important;
        font-size: 3rem;
        font-weight: 700;
        text-align: center;
        margin-bottom: 0.5rem;
        text-shadow: none;
    }
    
    .company-subtitle {
        color: #444;
        font-size: 1.2rem;
        text-align: center;
        font-weight: 300;
        margin-bottom: 1rem;
    }
    
    /* Card styling */
    .metric-card {
        background: linear-gradient(145deg, #ffffff, #f0f2f6);
        padding: 1.5rem;
        border-radius: 15px;
        box-shadow: 5px 5px 15px rgba(0,0,0,0.1), -5px -5px 15px rgba(255,255,255,0.7);
        margin-bottom: 1rem;
        border: 1px solid rgba(255,255,255,0.2);
        color: #222 !important;
    }
    /* Make all text inside metric-card dark */
    .metric-card h1, .metric-card h2, .metric-card h3, .metric-card h4, .metric-card h5, .metric-card h6,
    .metric-card p, .metric-card span, .metric-card div, .metric-card li, .metric-card label {
        color: #222 !important;
    }
    
    .feature-card {
        background: linear-gradient(145deg, #2c3e50, #34495e);
        padding: 1rem;
        border-radius: 15px;
        color: white;
        margin-bottom: 1rem;
        box-shadow: 0 8px 25px rgba(0,0,0,0.2);
        border: 1px solid rgba(255,255,255,0.1);
        transition: transform 0.3s ease;
    }
    
    .feature-card:hover {
        transform: translateY(-5px);
    }
    
    /* Button styling */
    .stButton > button {
        background: linear-gradient(45deg, #FF6B6B, #FF8E8E);
        color: white;
        border: none;
        padding: 0.75rem 2rem;
        border-radius: 25px;
        font-weight: 600;
        font-size: 1rem;
        transition: all 0.3s ease;
        box-shadow: 0 4px 15px rgba(255, 107, 107, 0.3);
    }
    
    .stButton > button:hover {
        background: linear-gradient(45deg, #FF5555, #FF7777);
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(255, 107, 107, 0.4);
    }
    
    /* Sidebar styling */
    .css-1d391kg {
        background: linear-gradient(180deg, #2c3e50 0%, #34495e 100%);
    }
    
    .css-1d391kg .css-1v0mbdj {
        color: white;
    }
    
    /* Progress bar styling */
    .stProgress > div > div {
        background: linear-gradient(90deg, #4CAF50, #8BC34A);
    }
    
    /* Tabs styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    
    .stTabs [data-baseweb="tab"] {
        background: linear-gradient(145deg, #e3f2fd, #bbdefb);
        border-radius: 10px;
        padding: 0.5rem 1rem;
        font-weight: 600;
    }
    
    .stTabs [aria-selected="true"] {
        background: linear-gradient(145deg, #2196f3, #1976d2);
        color: white;
    }
    
    /* Animation for success messages */
    @keyframes slideIn {
        from { transform: translateX(-100%); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
    }
    
    .success-animation {
        animation: slideIn 0.5s ease-out;
    }
    
    /* Logo styling */
    .logo-container {
        display: flex;
        justify-content: center;
        align-items: center;
        padding: 1rem;
    }
    
    .logo-container img {
        max-width: 150px;
        height: auto;
        filter: drop-shadow(0 4px 8px rgba(0,0,0,0.3));
    }
    
    /* Stats cards */
    .stats-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 1rem;
        margin: 2rem 0;
    }
    
    .stat-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1.5rem;
        border-radius: 15px;
        text-align: center;
        box-shadow: 0 8px 25px rgba(102, 126, 234, 0.3);
    }
    
    .stat-number {
        font-size: 2.5rem;
        font-weight: 700;
        margin-bottom: 0.5rem;
    }
    
    .stat-label {
        font-size: 1rem;
        opacity: 0.9;
        font-weight: 300;
    }
    .stTabs [role="tab"] {
        color: #222 !important;
    }
    .stTabs [aria-selected="true"] {
        color: #222 !important;
    }
    </style>
    """, unsafe_allow_html=True)

def create_header():
    """Create the application header with company branding"""
    st.markdown("""
    <div class="header-container">
        <div class="logo-container">
            <img src="https://gnpconsultancy.com/wp-content/uploads/2024/03/Logo.png.svg" alt="GNP Consultancies Logo" onerror="this.style.display='none'">
        </div>
        <h1 class="company-title">🗺️ GNP Scraper</h1>
        <p class="company-subtitle">Professional Google Maps Data Extraction Platform</p>
        <p class="company-subtitle">Powered by GNP Consultancies</p>
    </div>
    """, unsafe_allow_html=True)

def create_stats_dashboard(df):
    """Create a beautiful stats dashboard"""
    if not df.empty:
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown(f"""
            <div class="stat-card">
                <div class="stat-number">{len(df)}</div>
                <div class="stat-label">Total Businesses</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            phone_count = df['phone'].notna().sum()
            st.markdown(f"""
            <div class="stat-card">
                <div class="stat-number">{phone_count}</div>
                <div class="stat-label">With Phone</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            email_count = df['email'].notna().sum()
            st.markdown(f"""
            <div class="stat-card">
                <div class="stat-number">{email_count}</div>
                <div class="stat-label">With Email</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col4:
            website_count = df['website'].notna().sum()
            st.markdown(f"""
            <div class="stat-card">
                <div class="stat-number">{website_count}</div>
                <div class="stat-label">With Website</div>
            </div>
            """, unsafe_allow_html=True)

def create_extraction_progress_ui():
    """Create a beautiful progress tracking interface"""
    st.markdown("""
    <div class="feature-card">
        <h3>🚀 Extraction Progress</h3>
        <p>Real-time tracking of data extraction process</p>
    </div>
    """, unsafe_allow_html=True)

def main():
    st.set_page_config(
        page_title="GNP Consultancies - Maps Scraper",
        page_icon="🗺️",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Load custom CSS
    load_custom_css()
    
    # Create header
    create_header()
    
    # Sidebar for settings
    st.sidebar.markdown("""
    <div class="feature-card">
        <h2>⚙️ Extraction Settings</h2>
        <p>Configure your data extraction parameters</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Search query input with enhanced styling
    search_query = st.sidebar.text_input(
        "🔍 Search Query",
        placeholder="e.g., restaurants in New York",
        help="Enter your Google Maps search query",
        key="search_input"
    )
    
    # Max results setting
    max_results = st.sidebar.number_input(
        "📊 Maximum Results",
        min_value=1,
        max_value=200,
        value=20,
        help="Maximum number of results to extract per batch"
    )
    
    # Headless mode setting
    headless_mode = st.sidebar.checkbox(
        "🤖 Headless Mode",
        value=True,
        help="Run browser in background (recommended for performance)"
    )
    
    # Advanced settings in expander
    with st.sidebar.expander("🔧 Advanced Settings", expanded=False):
        delay_between_extractions = st.slider(
            "Delay Between Extractions (seconds)",
            min_value=0.1,
            max_value=3.0,
            value=0.5,
            step=0.1,
            help="Delay between each business extraction"
        )
        
        retry_attempts = st.number_input(
            "Retry Attempts",
            min_value=1,
            max_value=5,
            value=3,
            help="Number of retry attempts for failed extractions"
        )
    
    # Initialize session state
    if 'results' not in st.session_state:
        st.session_state.results = []
    if 'extraction_running' not in st.session_state:
        st.session_state.extraction_running = False
    if 'extraction_history' not in st.session_state:
        st.session_state.extraction_history = []
    
    # Main content area with tabs
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Dashboard", "🔍 Extraction", "📈 Analytics", "📋 History"])
    
    with tab1:
        st.markdown("""
        <div class="feature-card">
            <h2>🎯 Welcome to GNP Scraper</h2>
            <p>Your professional solution for Google Maps data extraction. Extract business information including names, phone numbers, emails, websites, addresses, and ratings with ease.</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Stats dashboard
        if st.session_state.results:
            df = pd.DataFrame(st.session_state.results)
            create_stats_dashboard(df)
            
            # Recent extractions preview
            st.subheader("🏢 Recent Extractions")
            recent_df = df.tail(10)
            st.dataframe(
                recent_df[['name', 'phone', 'email', 'rating', 'category']].fillna('N/A'),
                use_container_width=True
            )
        else:
            st.markdown("""
            <div class="metric-card">
                <h3>🚀 Ready to Start</h3>
                <p>Enter a search query and begin extracting valuable business data from Google Maps!</p>
            </div>
            """, unsafe_allow_html=True)
    
    with tab2:
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.markdown("""
            <div class="feature-card">
                <h2>📊 Extraction Results</h2>
            </div>
            """, unsafe_allow_html=True)
            
            # Results display
            if st.session_state.results:
                df = pd.DataFrame(st.session_state.results)
                
                # Enhanced results table
                st.dataframe(
                    df.style.highlight_max(axis=0, subset=['rating']),
                    use_container_width=True,
                    height=400
                )
                
                # Download section with multiple formats
                st.markdown("""
                <div class="feature-card">
                    <h3>📥 Export Options</h3>
                </div>
                """, unsafe_allow_html=True)
                
                col_dl1, col_dl2, col_dl3 = st.columns(3)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                
                with col_dl1:
                    csv = df.to_csv(index=False)
                    st.download_button(
                        label="📊 Download CSV",
                        data=csv,
                        file_name=f"gnp_scraper_results_{timestamp}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                
                with col_dl2:
                    excel_buffer = pd.ExcelWriter(f'gnp_scraper_results_{timestamp}.xlsx', engine='xlsxwriter')
                    df.to_excel(excel_buffer, sheet_name='Results', index=False)
                    excel_buffer.close()
                    
                with col_dl3:
                    json_data = df.to_json(orient='records', indent=2)
                    st.download_button(
                        label="📄 Download JSON",
                        data=json_data,
                        file_name=f"gnp_scraper_results_{timestamp}.json",
                        mime="application/json",
                        use_container_width=True
                    )
            
            elif not st.session_state.results and not st.session_state.extraction_running:
                st.markdown("""
                <div class="metric-card">
                    <h3>🎯 Get Started</h3>
                    <p>Configure your search parameters in the sidebar and click 'Start Extraction' to begin collecting business data.</p>
                </div>
                """, unsafe_allow_html=True)
        
        with col2:
            st.markdown("""
            <div class="feature-card">
                <h2>🚀 Controls</h2>
            </div>
            """, unsafe_allow_html=True)
            
            # Start extraction button
            if st.button(
                "🔍 Start Extraction",
                disabled=st.session_state.extraction_running or not search_query,
                type="primary",
                use_container_width=True
            ):
                if search_query:
                    st.session_state.extraction_running = True
                    
                    # Create beautiful progress interface
                    progress_container = st.container()
                    
                    with progress_container:
                        # Animated progress section
                        st.markdown("""
                        <div class="feature-card success-animation">
                            <h3>🔄 Extraction in Progress</h3>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # Progress components
                        main_progress = st.progress(0)
                        
                        col_prog1, col_prog2 = st.columns(2)
                        
                        with col_prog1:
                            stage_status = st.empty()
                            current_status = st.empty()
                        
                        with col_prog2:
                            extracted_count = st.empty()
                            company_display = st.empty()
                        
                        # Live results section
                        st.markdown("### 🏢 Live Extraction Feed")
                        recent_companies = st.empty()
                        live_results_container = st.empty()
                        
                        def update_progress(progress_info):
                            """Enhanced progress update with animations"""
                            try:
                                # Update main progress bar
                                if progress_info['total'] > 0:
                                    progress_value = progress_info['current'] / progress_info['total']
                                    main_progress.progress(min(progress_value, 1.0))
                                
                                # Update status with enhanced styling
                                stage = progress_info.get('stage', 'processing')
                                stage_icons = {
                                    'searching': '🔍',
                                    'found_results': '📋',
                                    'processing': '⚙️',
                                    'extracting': '🔍',
                                    'success': '✅',
                                    'failed': '⚠️',
                                    'error': '❌',
                                    'scrolling': '📜',
                                    'completed': '🎉'
                                }
                                
                                icon = stage_icons.get(stage, '⚙️')
                                stage_status.markdown(f"""
                                <div class="metric-card">
                                    <h4>{icon} {stage.replace('_', ' ').title()}</h4>
                                </div>
                                """, unsafe_allow_html=True)
                                
                                current_status.info(progress_info['status'])
                                
                                # Update metrics
                                extracted_count.metric(
                                    "🎯 Extracted", 
                                    progress_info['extracted'],
                                    delta=f"{progress_info['current']}/{progress_info['total']}"
                                )
                                
                                # Company display with enhanced styling
                                if 'company_name' in progress_info:
                                    company_display.markdown(f"""
                                    <div class="metric-card success-animation">
                                        <h4>🏢 {progress_info['company_name']}</h4>
                                    </div>
                                    """, unsafe_allow_html=True)
                                
                                # Update live feed
                                if hasattr(st.session_state, 'temp_results') and st.session_state.temp_results:
                                    recent_list = []
                                    for idx, result in enumerate(st.session_state.temp_results[-5:], 1):
                                        name = result.get('name', 'Unknown')
                                        phone = result.get('phone', 'N/A')
                                        rating = result.get('rating', 'N/A')
                                        category = result.get('category', 'N/A')
                                        
                                        recent_list.append(f"""
                                        **{idx}.** **{name}**  
                                        📞 {phone} | ⭐ {rating} | 🏷️ {category}
                                        """)
                                    
                                    recent_companies.markdown('\n\n'.join(recent_list))
                                    
                                    # Live table update
                                    live_df = pd.DataFrame(st.session_state.temp_results)
                                    live_results_container.dataframe(
                                        live_df[['name', 'phone', 'email', 'rating', 'category']].fillna('N/A'),
                                        use_container_width=True
                                    )
                                
                            except Exception as e:
                                st.error(f"Progress update error: {str(e)}")
                        
                        try:
                            # Initialize extraction
                            st.session_state.temp_results = []
                            extractor = GoogleMapsExtractorStreamlit(headless=headless_mode)
                            
                            def progress_with_results(progress_info):
                                update_progress(progress_info)
                                
                                if progress_info.get('stage') == 'success' and 'company_name' in progress_info:
                                    if hasattr(extractor, 'results') and extractor.results:
                                        latest_result = extractor.results[-1]
                                        if latest_result not in st.session_state.temp_results:
                                            st.session_state.temp_results.append(latest_result)
                            
                            # Start extraction
                            results, message = run_extraction_batch(
                                extractor, 
                                search_query, 
                                max_results, 
                                progress_with_results
                            )
                            
                            # Final results
                            if results:
                                st.session_state.results.extend(results)
                                
                                # Add to history
                                st.session_state.extraction_history.append({
                                    'timestamp': datetime.now(),
                                    'query': search_query,
                                    'results_count': len(results),
                                    'status': 'Success'
                                })
                                
                                main_progress.progress(1.0)
                                
                                # Success celebration
                                st.balloons()
                                st.markdown(f"""
                                <div class="feature-card success-animation">
                                    <h2>🎉 Extraction Completed Successfully!</h2>
                                    <p>Successfully extracted <strong>{len(results)}</strong> business records</p>
                                </div>
                                """, unsafe_allow_html=True)
                                
                            else:
                                st.error(f"❌ Extraction failed: {message}")
                                st.session_state.extraction_history.append({
                                    'timestamp': datetime.now(),
                                    'query': search_query,
                                    'results_count': 0,
                                    'status': f'Failed: {message}'
                                })
                        
                        except Exception as e:
                            st.error(f"❌ Extraction failed: {str(e)}")
                        
                        finally:
                            st.session_state.extraction_running = False
                            if hasattr(st.session_state, 'temp_results'):
                                del st.session_state.temp_results
                            time.sleep(1)
                            st.rerun()
            
            # Control buttons
            col_btn1, col_btn2 = st.columns(2)
            
            with col_btn1:
                if st.button(
                    "🗑️ Clear Results",
                    disabled=st.session_state.extraction_running,
                    use_container_width=True
                ):
                    st.session_state.results = []
                    st.success("🧹 Results cleared!")
                    st.rerun()
            
            with col_btn2:
                if st.session_state.results and not st.session_state.extraction_running:
                    if st.button(
                        "➕ Extract More",
                        disabled=not search_query,
                        use_container_width=True
                    ):
                        # Add more results logic here
                        pass
            
            # System status
            st.markdown("""
            <div class="feature-card">
                <h3>🔧 System Status</h3>
            </div>
            """, unsafe_allow_html=True)
            
            if st.button("🧪 Test ChromeDriver", use_container_width=True):
                with st.spinner("Testing browser connection..."):
                    try:
                        test_extractor = GoogleMapsExtractorStreamlit(headless=True)
                        success, message = test_extractor.initialize_driver()
                        
                        if success:
                            st.success("✅ ChromeDriver is working correctly!")
                            test_extractor.close()
                        else:
                            st.error(f"❌ ChromeDriver test failed: {message}")
                            st.info("💡 Try installing: pip install webdriver-manager")
                    except Exception as e:
                        st.error(f"❌ Browser test failed: {str(e)}")
    
    with tab3:
        st.markdown("""
        <div class="feature-card">
            <h2>📈 Data Analytics</h2>
            <p>Comprehensive analysis of your extracted data</p>
        </div>
        """, unsafe_allow_html=True)
        
        if st.session_state.results:
            df = pd.DataFrame(st.session_state.results)
            charts = create_analytics_charts(df)
            
            # Display charts
            if charts:
                col_chart1, col_chart2 = st.columns(2)
                
                with col_chart1:
                    if 'rating' in charts:
                        st.plotly_chart(charts['rating'], use_container_width=True)
                    if 'contact' in charts:
                        st.plotly_chart(charts['contact'], use_container_width=True)
                
                with col_chart2:
                    if 'category' in charts:
                        st.plotly_chart(charts['category'], use_container_width=True)
            
            # Data quality metrics
            st.subheader("📊 Data Quality Metrics")
            
            col_qual1, col_qual2, col_qual3, col_qual4 = st.columns(4)
            
            total_records = len(df)
            completeness_scores = {}
            
            for col in ['phone', 'email', 'website', 'address']:
                if col in df.columns:
                    completeness = (df[col].notna().sum() / total_records) * 100
                    completeness_scores[col] = completeness
            
            with col_qual1:
                phone_score = completeness_scores.get('phone', 0)
                st.metric("📞 Phone Completeness", f"{phone_score:.1f}%")
            
            with col_qual2:
                email_score = completeness_scores.get('email', 0)
                st.metric("📧 Email Completeness", f"{email_score:.1f}%")
            
            with col_qual3:
                website_score = completeness_scores.get('website', 0)
                st.metric("🌐 Website Completeness", f"{website_score:.1f}%")
            
            with col_qual4:
                address_score = completeness_scores.get('address', 0)
                st.metric("📍 Address Completeness", f"{address_score:.1f}%")
        
        else:
            st.info("📊 No data available for analysis. Start an extraction to see analytics.")
    
    with tab4:
        st.markdown("""
        <div class="feature-card">
            <h2>📋 Extraction History</h2>
            <p>Track your extraction activities and performance</p>
        </div>
        """, unsafe_allow_html=True)
        
        if st.session_state.extraction_history:
            history_df = pd.DataFrame(st.session_state.extraction_history)
            
            # Display history table
            st.dataframe(
                history_df.sort_values('timestamp', ascending=False),
                use_container_width=True
            )
            
            # History statistics
            col_hist1, col_hist2, col_hist3 = st.columns(3)
            
            with col_hist1:
                total_extractions = len(history_df)
                st.metric("Total Extractions", total_extractions)
            
            with col_hist2:
                successful_extractions = len(history_df[history_df['status'] == 'Success'])
                st.metric("Successful Extractions", successful_extractions)
            
            with col_hist3:
                total_records = history_df['results_count'].sum()
                st.metric("Total Records Extracted", total_records)
        
        else:
            st.info("📝 No extraction history available yet.")
    
    # Footer
    st.markdown("""
    <div class="feature-card" style="margin-top: 3rem;">
        <div style="text-align: center;">
            <h3>🏢 GNP Consultancies</h3>
            <p>Professional Data Solutions | Advanced Web Scraping Technology</p>
            <p><em>Empowering businesses with actionable data insights</em></p>
        </div>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
