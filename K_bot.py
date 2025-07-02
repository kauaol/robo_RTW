import time
from datetime import datetime
import numpy as np
import pandas as pd
from tqdm import tqdm
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    ElementClickInterceptedException,
)
from webdriver_manager.chrome import ChromeDriverManager
from colorama import init, Fore, Style
from tabulate import tabulate

def login(driver, url, usuario, senha):
    driver.get(url)
    try:
        username_field = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, '/html/body/div[2]/main/div[2]/div/div/div[2]/form/div[1]/div[3]/div[2]/div[2]/span/input'))
        )

        username_field.send_keys(usuario)

        botao = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, '/html/body/div[2]/main/div[2]/div/div/div[2]/form/div[2]/input'))
        )
        botao.click()

        botaoSenha = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, '/html/body/div[2]/main/div[2]/div/div/div[2]/form/div[1]/div[4]/div/div[2]/span/input'))
        )
        botaoSenha.clear()
        botaoSenha.send_keys(senha)
        botaoSenha.send_keys(Keys.RETURN)

        print("Login realizado com sucesso!")

    except (TimeoutException, NoSuchElementException) as e:
        print(f"Erro no login: {e}")
        raise

def extrair_pedidos(driver, max_paginas=None):
    dados = []
    contador = 0

    while True:

        if max_paginas is not None and contador >= max_paginas:
            print(f"Limite de {max_paginas} páginas atingido.")
            break

        try:
            tabela = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, 'andes-table__body'))
            )

            linhas = tabela.find_elements(By.TAG_NAME, 'tr')

            for linha in linhas:
                colunas = linha.find_elements(By.TAG_NAME, 'td')
                if len(colunas) >= 7:
                    dados.append({
                        "ID": colunas[0].text,
                        "Process Path": colunas[2].text,
                        "Unidades": colunas[4].text,
                        "Ultima Alteração": colunas[5].text,
                        "ETD": colunas[6].text
                    })

            botoes = driver.find_elements(By.TAG_NAME, "button")
            proximo_botao = None

            for botao in botoes:
                if botao.text.strip().lower() == "próxima página" and botao.is_enabled():
                    proximo_botao = botao
                    break

            if proximo_botao:
                proximo_botao.click()
                contador += 1
                time.sleep(1)
            else:
                print("Última página atingida.")
                break

        except (NoSuchElementException, TimeoutException, ElementClickInterceptedException) as e:
            print(f"Erro ou fim das páginas: {e}")
            break

    df = pd.DataFrame(dados)
    df.to_csv("pedidos.csv", index=False)
    #print(df)
    return df

def processar_pedidos(driver, ids):
    melis = []

    for id_ in tqdm(ids, desc="Processando Pedidos"):
        url = f"https://wms.adminml.com/reports/groups/order/{id_}/trace"
        driver.get(url)

        try:
            tabela = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (By.XPATH, '//*[@id="root-app"]/div[2]/section/section[2]/section[2]/table'))
            )

            if tabela:
                linhas = tabela.find_elements(By.TAG_NAME, "tr")

                for linha in linhas:
                    colunas = linha.find_elements(By.TAG_NAME, "td")

                    if len(colunas) >= 3:
                        melis.append({
                            "Pedido": id_,
                            "MELI": colunas[1].text.strip(),
                            "Unidades": colunas[2].text.strip(),
                        })

            else:
                print("Tabela não localizada")

            #print(f"Processado pedido {id_}")

        except TimeoutException:
            print(f"Timeout ao processar pedido {id_}")
            time.sleep(1)

    df = pd.DataFrame(melis)
    #print(df)
    df.to_csv("melis_sku.csv", index=False)

def processar_melis(driver, limite=None):
    melis = pd.read_csv("melis_sku.csv")
    melis_unicos = melis["MELI"].dropna().unique().tolist()

    if limite is not None:
        melis_unicos = melis_unicos[:limite]

    enderecos = []

    for meli in tqdm(melis_unicos, desc="Processando MELIs"):
        url = f"https://wms.adminml.com/reports/skus/{meli}"
        driver.get(url)

        try:
            tabela = WebDriverWait(driver, 2).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '.andes-table.table'))
            )

            linhas = tabela.find_elements(By.TAG_NAME, 'tr')

            encontrou_dados = False

            for linha in linhas:
                colunas = linha.find_elements(By.TAG_NAME, "td")
                if len(colunas) >= 7:
                    encontrou_dados = True
                    enderecos.append({
                        "MELI": meli,
                        "Posicao": colunas[1].text.strip(),
                        "Quantidade_disponivel": colunas[5].text.strip(),
                        "Quantidade_reservada": colunas[6].text.strip().split("\n")[0],
                    })

            if not encontrou_dados:
                enderecos.append({
                    "MELI": meli,
                    "Posicao": None,
                    "Quantidade_disponivel": None,
                    "Quantidade_reservada": None,
                })

        except Exception as e:
            # Se nem a tabela foi encontrada, também adiciona com Non
            #print(f"Tabela não encontrada para MELI {meli}. Pulando dados, mas registrando MELI.")
            enderecos.append({
                "MELI": meli,
                "Posicao": None,
                "Quantidade_disponivel": None,
                "Quantidade_reservada": None,
            })

    df = pd.DataFrame(enderecos)
    df.to_csv("enderecos.csv", index=False)
    #print(df)

def analisar_arquivos():

    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    pd.set_option('display.max_colwidth', None)

    # --- Leitura dos arquivos diretamente ---
    pedidos = pd.read_csv("pedidos.csv")
    melis = pd.read_csv("melis_sku.csv")
    enderecos = pd.read_csv("enderecos.csv")

    # --- Classificação das posições ---
    regras = {
        'MZ': 'Área Vendável',
        'PW': 'Área Vendável',
        'BL-500': 'Não Vendável',
        'BL-600': 'Não Vendável',
        'BL-700': 'Não Vendável',
        'BL-2': 'Não Vendável',
        'RS': 'Área Vendável',
        'BL': 'Área Vendável',
        'RR': 'Não Vendável',
        'MU': 'Não Vendável',
        'RK': 'Não Vendável',
        'RK-2': 'Não Vendável'
    }

    def classificar_posicao(posicao):
        if pd.isna(posicao):
            return 'Indefinido'
        for prefixo, classificacao in regras.items():
            if posicao.startswith(prefixo):
                return classificacao
        if posicao.startswith('MU'):
            if 'RC' in posicao:
                return 'Não Vendável'
            else:
                return 'Área Vendável'
        return 'Lógica Indefinida'

    enderecos['Classificacao'] = enderecos['Posicao'].apply(classificar_posicao)
    vendavel = enderecos[enderecos['Classificacao'] == 'Área Vendável'].copy()

    # --- Ajustar tipos numéricos ---
    melis['Unidades'] = pd.to_numeric(melis['Unidades'], errors='coerce').fillna(0).astype(int)
    vendavel['Quantidade_disponivel'] = pd.to_numeric(vendavel['Quantidade_disponivel'], errors='coerce').fillna(
        0).astype(int)

    # --- Calcular demanda e estoque ---
    demanda = melis.groupby('MELI')['Unidades'].sum().reset_index()
    estoque = vendavel.groupby('MELI')['Quantidade_disponivel'].sum().reset_index()

    # --- Merge demanda x estoque ---
    comparativo = demanda.merge(estoque, on='MELI', how='left').fillna(0)
    comparativo['Quantidade_disponivel'] = comparativo['Quantidade_disponivel'].astype(int)

    # --- Diferença e disponibilidade ---
    comparativo['Diferença'] = comparativo['Quantidade_disponivel'] - comparativo['Unidades']
    comparativo['Disponibilidade'] = np.where(comparativo['Diferença'] >= 0, 'Suficiente', 'Insuficiente')

    # --- Agrupar pedidos ---
    pedidos_agrupados = melis.groupby('MELI')['Pedido'].apply(list).reset_index()

    # --- Merge final ---
    comparativo = comparativo.merge(pedidos_agrupados, on='MELI', how='left')
    comparativo = comparativo.sort_values('Disponibilidade', ascending=True).reset_index(drop=True)

    comparativo.to_csv("comparativo.csv", index=False)

    comparativo = pd.read_csv("comparativo.csv")

    #print(comparativo)

if __name__ == "__main__":
    init(autoreset=True)

    print(f"{Fore.CYAN}{Style.BRIGHT}-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=")
    print(f"{Fore.YELLOW}{Style.BRIGHT}LOGIN")
    print(f"{Fore.CYAN}{Style.BRIGHT}-=-=-=-=-=-=-=-=-=-=-=-=-=-=-={Style.RESET_ALL}")

    usuario = input(f"{Fore.GREEN}Digite seu usuário: {Style.RESET_ALL}")
    senha = input(f"{Fore.GREEN}Digite sua senha: {Style.RESET_ALL}")

    # Configurações do Chrome
    chrome_options = Options()
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--log-level=3")
    # chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-images")
    chrome_options.add_argument("--disable-infobars")

    # Inicia o navegador
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    try:
        # Faz login só uma vez
        print("iniciando login")
        login(driver, "https://wms.adminml.com/", usuario, senha)

        while True:
            hora_sla = input(f"\n{Fore.GREEN}Digite o ETD (00:00:00): {Style.RESET_ALL}")
            data_atual = input(f"{Fore.GREEN}Digite a data (yyyy-mm-dd): {Style.RESET_ALL}")

            print(f"\n{Fore.CYAN}{Style.BRIGHT}-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=")
            print(f"{Fore.YELLOW}{Style.BRIGHT}ESCOLHA O PROCESS PATH")
            print(f"{Fore.CYAN}{Style.BRIGHT}-=-=-=-=-=-=-=-=-=-=-=-=-=-=-={Style.RESET_ALL}")

            print(f"{Fore.BLUE}0 - {Fore.WHITE}TODOS")
            print(f"{Fore.BLUE}1 - {Fore.WHITE}NON TOTABLE MULTI ORDER")
            print(f"{Fore.BLUE}2 - {Fore.WHITE}TOTABLE MONO")
            print(f"{Fore.BLUE}3 - {Fore.WHITE}NON TOTABLE SINGLE SKU")
            print(f"{Fore.BLUE}4 - {Fore.WHITE}TOTABLE MULTI BATCH")
            print(f"{Fore.BLUE}5 - {Fore.WHITE}NON TOTABLE MONO")
            print(f"{Fore.BLUE}6 - {Fore.WHITE}TOTABLE SINGLE SKU")

            escolha = input(f"\n{Fore.GREEN}Digite o número correspondente: {Style.RESET_ALL}")

            analise = ""
            process_path = ""

            if escolha == "0":
                analise = "1"
            elif escolha == "1":
                analise = "2"
                process_path = "NON_TOT_MULTI_ORDER"
            elif escolha == "2":
                analise = "2"
                process_path = "TOT_MONO"
            elif escolha == "3":
                analise = "2"
                process_path = "NON_TOT_SINGLE_SKU"
            elif escolha == "4":
                analise = "2"
                process_path = "TOT_MULTI_BATCH"
            elif escolha == "5":
                analise = "2"
                process_path = "NON_TOT_MONO"
            elif escolha == "6":
                analise = "2"
                process_path = "TOT_SINGLE_SKU"
            else:
                print("Opção inválida. Pulando essa rodada.")
                continue

            if analise == "1":
                url = (
                    f"https://wms.adminml.com/reports/units/orders?"
                    f"std_from={data_atual}T{hora_sla}&std_to={data_atual}T{hora_sla}"
                    f"&group_type=order&unit_status=pending,temp_unavailable"
                )
            else:
                url = (
                    f"https://wms.adminml.com/reports/units/orders?"
                    f"process_path={process_path}&std_from={data_atual}T{hora_sla}&std_to={data_atual}T{hora_sla}"
                    f"&group_type=order&unit_status=pending,temp_unavailable"
                )

            # Execução para o loop atual
            driver.get(url)
            df_pedidos = extrair_pedidos(driver)
            primeiros_ids = df_pedidos["ID"].dropna().unique().tolist()
            processar_pedidos(driver, primeiros_ids)
            processar_melis(driver)
            analisar_arquivos()

            print(f"\n{Fore.GREEN}Arquivos processados com sucesso!")

            continuar = input(f"\n{Fore.YELLOW}Deseja fazer outra consulta? (s/n): {Style.RESET_ALL}")
            if continuar.lower() != "s":
                break

    except Exception as e:
        print(f"{Fore.RED}Erro durante a execução: {e}")

    finally:
        driver.quit()


