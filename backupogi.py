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

def main():
    st.set_page_config(
        page_title="Google Maps Data Extractor",
        page_icon="🗺️",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    st.title("🗺️ Google Maps Data Extractor")
    st.markdown("Extract business information from Google Maps search results")
    
    # Sidebar for settings
    st.sidebar.header("⚙️ Settings")
    
    # Search query input
    search_query = st.sidebar.text_input(
        "Search Query",
        placeholder="e.g., restaurants in New York",
        help="Enter your Google Maps search query"
    )
    
    # Max results setting
    max_results = st.sidebar.number_input(
        "Maximum Results",
        min_value=1,
        max_value=100,
        value=20,
        help="Maximum number of results to extract per batch"
    )
    
    # Headless mode setting
    headless_mode = st.sidebar.checkbox(
        "Headless Mode",
        value=True,
        help="Run browser in background (recommended)"
    )
    
    # Initialize session state
    if 'results' not in st.session_state:
        st.session_state.results = []
    if 'extraction_running' not in st.session_state:
        st.session_state.extraction_running = False
    
    # Main content area
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.header("📊 Extraction Results")
        
        # Results display
        if st.session_state.results:
            st.success(f"✅ Found {len(st.session_state.results)} results!")
            
            # Convert to DataFrame
            df = pd.DataFrame(st.session_state.results)
            
            # Display results table
            st.dataframe(df, use_container_width=True)
            
            # Download section
            st.subheader("📥 Download Results")
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"google_maps_results_{timestamp}.csv"
            
            # Create download button
            csv = df.to_csv(index=False)
            st.download_button(
                label="📁 Download as CSV",
                data=csv,
                file_name=filename,
                mime="text/csv",
                key="download_csv"
            )
            
            # Summary statistics
            st.subheader("📈 Summary Statistics")
            col_stats1, col_stats2, col_stats3, col_stats4 = st.columns(4)
            
            with col_stats1:
                st.metric("Total Results", len(df))
            
            with col_stats2:
                phone_count = df['phone'].notna().sum()
                st.metric("With Phone", phone_count)
            
            with col_stats3:
                email_count = df['email'].notna().sum()
                st.metric("With Email", email_count)
            
            with col_stats4:
                website_count = df['website'].notna().sum()
                st.metric("With Website", website_count)
        
        elif not st.session_state.results and not st.session_state.extraction_running:
            st.info("👆 Enter a search query and click 'Start Extraction' to begin")
    
    with col2:
        st.header("🚀 Controls")
        
        # Start extraction button
        if st.button(
            "🔍 Start Extraction",
            disabled=st.session_state.extraction_running or not search_query,
            type="primary",
            use_container_width=True
        ):
            if search_query:
                st.session_state.extraction_running = True
                
                # Create dynamic progress containers
                progress_container = st.container()
                
                with progress_container:
                    # Main progress bar
                    main_progress = st.progress(0)
                    
                    # Status displays
                    col_status1, col_status2 = st.columns(2)
                    
                    with col_status1:
                        stage_status = st.empty()
                        current_status = st.empty()
                    
                    with col_status2:
                        extracted_count = st.empty()
                        company_display = st.empty()
                    
                    # Recent extractions display
                    st.subheader("🏢 Recently Extracted Companies")
                    recent_companies = st.empty()
                    
                    # Live results table
                    live_results_container = st.empty()
                    
                    def update_progress(progress_info):
                        """Update the UI with progress information"""
                        try:
                            # Update main progress bar
                            if progress_info['total'] > 0:
                                progress_value = progress_info['current'] / progress_info['total']
                                main_progress.progress(min(progress_value, 1.0))
                            
                            # Update status information
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
                            stage_status.info(f"{icon} Stage: {stage.replace('_', ' ').title()}")
                            
                            # Update current status
                            current_status.text(progress_info['status'])
                            
                            # Update extracted count
                            extracted_count.metric(
                                "Extracted", 
                                progress_info['extracted'],
                                delta=f"Progress: {progress_info['current']}/{progress_info['total']}"
                            )
                            
                            # Show current company being processed
                            if 'company_name' in progress_info:
                                company_display.success(f"🏢 **{progress_info['company_name']}**")
                            elif stage == 'extracting':
                                company_display.info("🔍 Analyzing business data...")
                            elif stage == 'processing':
                                company_display.info("⚙️ Processing listing...")
                            
                            # Update recent companies list
                            if hasattr(st.session_state, 'temp_results') and st.session_state.temp_results:
                                recent_list = []
                                for idx, result in enumerate(st.session_state.temp_results[-5:], 1):  # Show last 5
                                    name = result.get('name', 'Unknown')
                                    phone = result.get('phone', 'No phone')
                                    rating = result.get('rating', 'No rating')
                                    recent_list.append(f"**{idx}.** {name} | 📞 {phone} | ⭐ {rating}")
                                
                                recent_companies.markdown('\n\n'.join(recent_list))
                            
                            # Update live results table
                            if hasattr(st.session_state, 'temp_results') and st.session_state.temp_results:
                                live_df = pd.DataFrame(st.session_state.temp_results)
                                live_results_container.dataframe(live_df, use_container_width=True)
                            
                        except Exception as e:
                            st.error(f"Progress update error: {str(e)}")
                    
                    try:
                        # Initialize temporary results storage
                        st.session_state.temp_results = []
                        
                        # Create extractor
                        extractor = GoogleMapsExtractorStreamlit(headless=headless_mode)
                        
                        # Custom progress callback that updates temp results
                        def progress_with_results(progress_info):
                            update_progress(progress_info)
                            
                            # Add to temp results if we have a successful extraction
                            if progress_info.get('stage') == 'success' and 'company_name' in progress_info:
                                # Find the latest result and add it to temp results
                                if hasattr(extractor, 'results') and extractor.results:
                                    latest_result = extractor.results[-1]
                                    if latest_result not in st.session_state.temp_results:
                                        st.session_state.temp_results.append(latest_result)
                        
                        # Start extraction with progress updates
                        results, message = run_extraction_batch(
                            extractor, 
                            search_query, 
                            max_results, 
                            progress_with_results
                        )
                        
                        # Final update
                        if results:
                            st.session_state.results.extend(results)
                            main_progress.progress(1.0)
                            stage_status.success("🎉 Extraction Completed!")
                            current_status.success(f"Successfully extracted {len(results)} results!")
                            
                            # Show completion summary
                            st.balloons()
                            st.success(f"🎉 Successfully extracted {len(results)} businesses!")
                            
                        else:
                            st.error(f"❌ Extraction failed: {message}")
                        
                    except Exception as e:
                        st.error(f"❌ Extraction failed: {str(e)}")
                    
                    finally:
                        st.session_state.extraction_running = False
                        # Clean up temp results
                        if hasattr(st.session_state, 'temp_results'):
                            del st.session_state.temp_results
                        time.sleep(1)
                        st.rerun()
        
        # Clear results button
        if st.button(
            "🗑️ Clear Results",
            disabled=st.session_state.extraction_running,
            use_container_width=True
        ):
            st.session_state.results = []
            st.success("🧹 Results cleared!")
            st.rerun()
        
        # Add More Results button
        if st.session_state.results and not st.session_state.extraction_running:
            if st.button(
                "➕ Extract More Results",
                disabled=not search_query,
                use_container_width=True
            ):
                st.session_state.extraction_running = True
                
                with st.spinner("🔄 Extracting more results..."):
                    try:
                        extractor = GoogleMapsExtractorStreamlit(headless=headless_mode)
                        success, message = extractor.search_google_maps(search_query)
                        
                        if success:
                            results, extract_message = extractor.extract_single_batch(max_results)
                            
                            if results:
                                # Filter out duplicates based on name
                                existing_names = {r['name'] for r in st.session_state.results if r.get('name')}
                                new_results = [r for r in results if r.get('name') and r['name'] not in existing_names]
                                
                                st.session_state.results.extend(new_results)
                                st.success(f"🎉 Added {len(new_results)} new results!")
                            else:
                                st.warning("No additional results found.")
                        else:
                            st.error(f"❌ Search failed: {message}")
                        
                        extractor.close()
                        
                    except Exception as e:
                        st.error(f"❌ Extraction failed: {str(e)}")
                    
                    finally:
                        st.session_state.extraction_running = False
                        st.rerun()
        
        # Test connection section
        st.subheader("🔧 Test Browser Connection")
        if st.button("Test ChromeDriver", use_container_width=True):
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
        
        st.markdown("---")
        st.subheader("📋 Instructions")
        st.markdown("""
        1. **Enter Search Query**: Type your Google Maps search (e.g., "restaurants in Paris")
        2. **Set Max Results**: Choose how many results to extract per batch
        3. **Click Start**: Begin the extraction process
        4. **Wait**: The process will run and show progress
        5. **Download**: Save results as CSV when complete
        
        **Tips:**
        - Use specific search terms for better results
        - Headless mode is faster
        - Use "Extract More Results" to get additional data
        - Results include: name, phone, email, website, address, rating
        """)
        
        # Status info
        st.subheader("ℹ️ Status")
        if st.session_state.extraction_running:
            st.info("🔄 Extraction is running...")
        elif st.session_state.results:
            st.success(f"✅ Current results: {len(st.session_state.results)} entries")
        else:
            st.info("⏳ Ready to start extraction")

if __name__ == "__main__":
    main()
