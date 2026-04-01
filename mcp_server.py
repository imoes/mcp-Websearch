# Fügen Sie diese Importanweisung hinzu, falls noch nicht vorhanden
from flask_cors import CORS

# Fügen Sie diese Zeile hinzu, um CORS für http://localhost zu aktivieren
CORS(app, origins=["http://localhost"])