from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.service import Service
import pandas as pd
import time
import random
import subprocess
import os
import json
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
from datetime import datetime

# Inicializar Firebase con las credenciales
cred = credentials.Certificate('firebase-credentials.json')
try:
    firebase_admin.initialize_app(cred)
except ValueError:
    # La aplicación ya está inicializada
    pass

# Obtener la instancia de Firestore
db = firestore.client()

class BumeranScraper:
    def __init__(self):
        # Configurar opciones de Chrome
        self.options = webdriver.ChromeOptions()
        
        # Opciones para evitar detección
        self.options.add_experimental_option("excludeSwitches", ["enable-automation"])
        self.options.add_experimental_option('useAutomationExtension', False)
        self.options.add_argument('--disable-blink-features=AutomationControlled')
        self.options.add_argument('--disable-extensions')
        self.options.add_argument('--no-sandbox')
        self.options.add_argument('--disable-infobars')
        self.options.add_argument('--disable-dev-shm-usage')
        self.options.add_argument('--disable-browser-side-navigation')
        self.options.add_argument('--disable-gpu')
        self.options.add_argument('--start-maximized')
        self.options.add_argument('--ignore-certificate-errors')
        self.options.add_argument('--ignore-ssl-errors')
        self.options.add_argument(f'user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        # Verificar si Chrome está instalado
        try:
            chrome_path = subprocess.check_output(["which", "google-chrome"]).decode().strip()
        except:
            chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        
        if os.path.exists(chrome_path):
            self.options.binary_location = chrome_path
        
        # Inicializar el driver
        self.driver = webdriver.Chrome(options=self.options)
        
        # Configurar el CDP para evadir la detección
        self.driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            "platform": "MacOS"
        })
        
        # Eliminar webdriver de window.navigator
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        self.wait = WebDriverWait(self.driver, 20)

    def random_sleep(self, min_time=1, max_time=3):
        time.sleep(random.uniform(min_time, max_time))

    def scroll_to_element(self, element):
        self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
        self.random_sleep(0.5, 1)

    def get_total_pages(self):
        try:
            # Encontrar todos los enlaces de paginación
            pagination_links = self.driver.find_elements(By.CSS_SELECTOR, "div.sc-cGDfzg a")
            if pagination_links:
                # El último número es el total de páginas
                return int(pagination_links[-1].text)
        except Exception as e:
            print(f"Error al obtener el total de páginas: {str(e)}")
        return 1

    def scrape_all_pages(self, base_url):
        print(f"Accediendo a {base_url}")
        self.driver.get(base_url)
        all_jobs = []
        
        # Obtener el número total de páginas
        total_pages = self.get_total_pages()
        print(f"Total de páginas encontradas: {total_pages}")
        
        # Iterar sobre cada página
        for page in range(1, total_pages + 1):
            print(f"\nProcesando página {page} de {total_pages}")
            
            if page > 1:
                # Construir la URL de la página actual
                current_url = f"{base_url}?page={page}"
                print(f"Accediendo a {current_url}")
                self.driver.get(current_url)
            
            # Obtener los trabajos de la página actual
            page_jobs = self.scrape_jobs()
            if page_jobs:
                all_jobs.extend(page_jobs)
            
            # Pausa entre páginas para evitar sobrecarga
            self.random_sleep(2, 4)
        
        return all_jobs

    def scrape_jobs(self, url=None):
        if url and not hasattr(self, 'driver'):
            print(f"Accediendo a {url}")
            self.driver.get(url)
        
        jobs = []
        
        try:
            # Esperar a que la página cargue completamente
            self.random_sleep(5, 7)
            
            # Realizar scroll progresivo
            for i in range(3):
                self.driver.execute_script(f"window.scrollTo(0, {(i+1)*500});")
                self.random_sleep(1, 2)
            
            print("Buscando tarjetas de trabajo...")
            
            # Intentar diferentes selectores para las tarjetas de trabajo
            selectors = [
                "div[class*='sc-kXoVnq']",
                "div[class*='aviso']",
                "div[class*='job-card']",
                "div[class*='vacancy']",
                "//div[contains(@class, 'sc-') and .//h2]"  # XPath para buscar divs que contengan h2
            ]
            
            job_cards = None
            for selector in selectors:
                try:
                    if '//' in selector:  # Es un XPath
                        job_cards = self.wait.until(
                            EC.presence_of_all_elements_located((By.XPATH, selector))
                        )
                    else:  # Es un CSS Selector
                        job_cards = self.wait.until(
                            EC.presence_of_all_elements_located((By.CSS_SELECTOR, selector))
                        )
                    
                    if job_cards:
                        print(f"Encontradas {len(job_cards)} tarjetas de trabajo usando el selector: {selector}")
                        # Debug: imprimir el HTML de la primera tarjeta
                        print("HTML de la primera tarjeta:")
                        print(job_cards[0].get_attribute('outerHTML'))
                        break
                except Exception as e:
                    print(f"Selector {selector} no funcionó: {str(e)}")
                    continue

            if not job_cards:
                print("No se encontraron tarjetas de trabajo con ningún selector")
                # Guardar el HTML para debug
                with open('debug.html', 'w', encoding='utf-8') as f:
                    f.write(self.driver.page_source)
                print("HTML guardado en debug.html para análisis")
                return jobs

            for card in job_cards:
                try:
                    # Hacer scroll hasta el elemento
                    self.scroll_to_element(card)
                    
                    # Extraer información del trabajo con manejo de errores más detallado
                    try:
                        title = card.find_element(By.CSS_SELECTOR, "h2").text
                    except:
                        try:
                            title = card.find_element(By.CSS_SELECTOR, "[class*='title']").text
                        except:
                            title = "No disponible"
                            print("No se pudo extraer el título")
                    
                    try:
                        company = card.find_element(By.XPATH, ".//h3[contains(@class, 'sc-eLVolr')]").text
                    except:
                        try:
                            company = card.find_element(By.XPATH, ".//span[contains(@class, 'sc-iEPtyo')]//h3").text
                        except:
                            company = "No disponible"
                            print("No se pudo extraer la empresa")
                    
                    try:
                        location = card.find_element(By.XPATH, ".//span[contains(@class, 'sc-fPEBxH')]//h3").text
                    except:
                        try:
                            location = card.find_element(By.XPATH, ".//div[contains(@class, 'sc-cBXKeB')]//h3[contains(@class, 'sc-hWkyhb')]").text
                        except:
                            location = "No disponible"
                            print("No se pudo extraer la ubicación")
                    
                    try:
                        end_date = card.find_element(By.XPATH, ".//h3[contains(@class, 'sc-iLQbDB')]").text
                    except:
                        try:
                            end_date = card.find_element(By.XPATH, ".//div[contains(@class, 'sc-lmrgJh')]//h3").text
                        except:
                            end_date = "No disponible"
                            print("No se pudo extraer la fecha de publicación")
                    
                    try:
                        url = card.find_element(By.CSS_SELECTOR, "a").get_attribute("href")
                    except:
                        url = "No disponible"
                        print("No se pudo extraer el enlace")
                    
                    # Crear diccionario con la información estandarizada
                    job_info = {
                        'company': company,
                        'end_date': end_date,
                        'location': location,
                        'salary': "2025",
                        'title': title,
                        'url': url
                    }
                    
                    jobs.append(job_info)
                    print(f"Trabajo agregado: {title} en {company}")
                    
                    # Pequeña pausa entre cada tarjeta
                    self.random_sleep(0.5, 1)
                    
                except Exception as e:
                    print(f"Error al extraer información de una tarjeta: {str(e)}")
                    continue

        except TimeoutException:
            print("Tiempo de espera agotado al cargar los trabajos")
        except Exception as e:
            print(f"Error inesperado: {str(e)}")
            # Guardar el HTML para debug
            with open('error_debug.html', 'w', encoding='utf-8') as f:
                f.write(self.driver.page_source)
            print("HTML guardado en error_debug.html para análisis")
        
        return jobs

    def save_to_csv(self, jobs, filename='bumeran_jobs.csv'):
        if jobs:
            df = pd.DataFrame(jobs)
            df.to_csv(filename, index=False, encoding='utf-8')
            print(f"Datos guardados en {filename}")
            
            # También guardar como JSON para mejor visualización
            with open('bumeran_jobs.json', 'w', encoding='utf-8') as f:
                json.dump(jobs, f, ensure_ascii=False, indent=2)
            print("Datos también guardados en bumeran_jobs.json")
        else:
            print("No hay trabajos para guardar")

    def save_to_firebase(self, jobs):
        if not jobs:
            print("No hay trabajos para guardar en Firebase")
            return

        try:
            # Crear un nuevo documento en la colección extractions
            extraction_ref = db.collection('extractions').document()
            
            # Metadata del scraping
            extraction_data = {
                'extraction_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'source': 'bumeran.pe',
                'total': len(jobs),
                'total_practices': len(jobs),
                'max_pages': self.get_total_pages(),
                'use_selenium': True
            }
            
            # Guardar metadata
            extraction_ref.set(extraction_data)
            print(f"Metadata guardada en Firebase con ID: {extraction_ref.id}")
            
            # Crear una subcolección 'practices' para los trabajos
            practices_ref = extraction_ref.collection('practices')
            
            # Guardar cada trabajo como un documento en la subcolección
            for job in jobs:
                # Generar un ID único para el documento
                doc_ref = practices_ref.document()
                doc_ref.set(job)
            
            print(f"Se guardaron {len(jobs)} trabajos en Firebase")
            return extraction_ref.id
            
        except Exception as e:
            print(f"Error al guardar en Firebase: {str(e)}")
            return None

    def close(self):
        self.driver.quit()

def main():
    base_url = "https://www.bumeran.com.pe/en-lima/empleos-publicacion-menor-a-3-dias-busqueda-practicante.html"
    scraper = BumeranScraper()
    
    try:
        print("Iniciando scraping...")
        jobs = scraper.scrape_all_pages(base_url)
        
        # Guardar en CSV y JSON (local)
        scraper.save_to_csv(jobs)
        
        # Guardar en Firebase
        firebase_id = scraper.save_to_firebase(jobs)
        if firebase_id:
            print(f"Datos guardados exitosamente en Firebase con ID: {firebase_id}")
        
        print(f"Se encontraron y procesaron {len(jobs)} trabajos en total")
        
    except Exception as e:
        print(f"Error durante el scraping: {str(e)}")
    finally:
        scraper.close()

if __name__ == "__main__":
    main() 