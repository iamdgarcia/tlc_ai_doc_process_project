product_name = "Tea verde maracuyá O"

products_bbdd = ["tea verde maracuya","tea verde melocotón","tea limón", "cafe colombiano", "chocolate amargo", "infusion de manzanilla"]


#Normalizar entrada
#quitar tildes
product_name = product_name.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
#Texto en minísculas
product_name = product_name.lower()

## Forma determinista
print("Método determinista:")
found_determinista = False
for product in products_bbdd:
    if product_name == product:
        print(f"[DETERMINISTA] El producto {product_name} se encuentra en la base de datos.")
        found_determinista = True
        exit()

if not found_determinista:
    print(f"[DETERMINISTA] El producto {product_name} no se encuentra en la base de datos.")
print("\n\n")
# ----
# Fuzzy matching
print("Método fuzzy matching:")
from rapidfuzz import fuzz, process
fuzzy_threshold = 80  # Umbral de similitud (0-100)
results = process.extract(product_name, products_bbdd, scorer=fuzz.ratio, limit=3)
if results:
    print(f"[FUZZY MATCHING] Los productos más similares a '{product_name}' son:")
    for match in results:
        if match[1] >= fuzzy_threshold:
            print(f"- {match[0]} (similaridad: {match[1]}%)")