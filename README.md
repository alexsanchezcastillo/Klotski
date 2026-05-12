# Klotski AP2 - Memoria Tecnica

Projecte de resolucio de puzzles de peces lliscants mitjancant grafs.
L'objectiu principal es modelar l'espai d'estats d'un puzzle, trobar solucions minimes i avaluar l'interes dels puzzles per contribuir al repositori col.laboratiu.

## Objectiu del projecte

- Construir el graf d'estats d'un puzzle Klotski.
- Trobar una solucio com a sequencia de moviments.
- Analitzar propietats del graf per obtenir una puntuacio d'interes.
- Interaccionar amb l'API publica per descarregar, valorar i pujar puzzles.

## Estructura del codi

- [src/puzzle.py](src/puzzle.py): tipus i validacio de Puzzle, Piece i State.
- [src/logic.py](src/logic.py): simulacio de moviments valids i aplicacio de moviments.
- [src/play.py](src/play.py): joc interactiu en terminal/finestra.
- [src/image.py](src/image.py): render d'un estat en PNG.
- [src/movie.py](src/movie.py): render de la solucio en GIF.
- [src/3D_view.py](src/3D_view.py): visualitzacio 3D del graf d'estats.
- [src/download.py](src/download.py): descarrega de puzzles des del repositori.
- [src/graph.py](src/graph.py): construccio del graf d'estats i export a GraphML.
- [src/solve.py](src/solve.py): cerca del cami minim i export de la solucio a .sol.json.

## Model de dades

Format JSON del puzzle:

```json
{
  "W": 4,
  "H": 5,
  "walls": [[x, y], ...],
  "pieces": [[[rx, ry], ...], ...],
  "start": [[x, y], ...],
  "goals": [{"i": 0, "pos": [x, y]}, ...]
}
```

Criteris clau:

- Les peces es defineixen amb coordenades relatives normalitzades (sense valors negatius).
- La posicio de cada peca es la cantonada superior esquerra del rectangle contenidor.
- Un estat es la llista de posicions de totes les peces, en ordre canonic.
- Un puzzle esta resolt quan es compleixen tots els objectius.

Format de moviments (.sol.json):

```json
[[piece_index, "N"], [piece_index, "E"], ...]
```

## API del repositori

Base URL: https://klotski.pauek.dev

- GET /api/puzzles: retorna IDs de puzzles.
- GET /api/puzzles/<id>: retorna puzzle + estrelles.
- POST /api/puzzles: pujada de puzzle (requereix token).
- POST /api/puzzles/<id>/votes: enviament de vot (requereix token).

## Desenvolupament cronologic (apartat principal)

Aquest apartat descriu el projecte en l'ordre real de construccio.
Cada script inclou la seva finalitat i les comandes d'us.

### Pas 0 - Preparacio de l'entorn

Instal.lacio de dependències i preparacio de l'entorn de treball.

```bash
pixi install
```

### Pas 1 - download.py

Primer script implementat. Connecta amb l'API publica del repositori per obtenir la llista de puzzles disponibles i descarregar-los en format JSON.

El flux es el seguent:
1. GET /api/puzzles retorna una llista d'IDs (hash SHA-256 de cada puzzle).
2. Per cada ID, GET /api/puzzles/<id> retorna el puzzle en JSON.
3. Cada puzzle es valida amb Puzzle.from_json() per assegurar que el format es correcte.
4. Es desa a puzzles/<id>.json amb indentacio per facilitar la lectura.

Permet seleccionar IDs concrets o limitar el nombre de descàrregues. Si un puzzle falla (xarxa o format invalid), el reporta pero continua amb la resta.

Per consultar IDs directament des de l'API:

```bash
# Veure tots els identificadors
curl https://klotski.pauek.dev/api/puzzles

# Veure els primers 10 identificadors, formatats
curl -s https://klotski.pauek.dev/api/puzzles | jq '.[0:10]'

# Veure nomes el primer identificador
curl -s https://klotski.pauek.dev/api/puzzles | jq -r '.[0]'
```

```bash
# Descarregar el top complet (fins a 100)
pixi run python src/download.py

# Descarregar nomes N puzzles
pixi run python src/download.py --limit 10

# Descarregar un o varios IDs concrets
pixi run python src/download.py --id <ID>
pixi run python src/download.py --id <ID1> --id <ID2>

# Triar carpeta de sortida
pixi run python src/download.py --limit 10 --out altra_carpeta
```

### Pas 2 - graph.py

Segon script implementat. Construeix el graf d'estats accessibles des de l'estat inicial del puzzle.

Model utilitzat:
1. Node = un estat complet del puzzle (posicio de totes les peces).
2. Aresta = un moviment valid d'un sol pas entre dos estats.
3. Exploracio BFS des de l'estat inicial fins esgotar tots els estats accessibles.

Sortida:
- Fitxer `.graphml` per cada puzzle (per defecte amb el mateix nom del `.json`).
- El graf guarda metadades de node (`state`, `is_start`, `is_goal`) i el `puzzle` original.

Comandes:

```bash
# Crear el graf amb nom de sortida per defecte
pixi run python src/graph.py puzzles/sample3.json

# Crear el graf amb nom de sortida explicit
pixi run python src/graph.py puzzles/sample3.json puzzles/sample3.graphml
```

Nota de visualitzacio:
- Obrir directament un `.graphml` al navegador mostra XML (text), no una imatge.
- Per veure el graf en 3D, cal executar el visor `3D_view.py`.

```bash
# Veure el graf sense cami de solucio
pixi run python src/3D_view.py puzzles/sample3.graphml

# Veure el graf amb el cami de solucio ressaltat (groc)
pixi run python src/3D_view.py puzzles/sample3.graphml puzzles/sample3.sol.json
```

### Pas 3 - solve.py

Tercer script implementat. Troba una solucio minima sobre el graf d'estats i la desa en format `.sol.json`.

Funcionalitat principal:
1. Carrega el puzzle.
2. Carrega el graf `.graphml` si existeix.
3. Si el graf no existeix, el construeix automaticament.
4. Busca el cami mes curt des del node inicial fins a un node objectiu.
5. Converteix la sequencia d'estats a moviments `[peca, direccio]`.
6. Desa la solucio en un fitxer `.sol.json`.

Comandes:

```bash
# Mode minim: puzzle -> usa <puzzle>.graphml i desa <puzzle>.sol.json
pixi run python src/solve.py puzzles/sample3.json

# Indicant fitxer de graf explicit
pixi run python src/solve.py puzzles/sample3.json puzzles/sample3.graphml

# Indicant graf i nom de sortida de la solucio
pixi run python src/solve.py puzzles/sample3.json puzzles/sample3.graphml puzzles/sample3.sol.json
```

Validacio feta:
1. Compatible amb visualitzacio 3D del cami:

```bash
pixi run python src/3D_view.py puzzles/sample3.graphml puzzles/sample3.sol.json
```

2. Compatible amb render de pelicula GIF:

```bash
pixi run python src/movie.py puzzles/sample3.json puzzles/sample3.sol.json img/sample3.gif
```

### Eines de suport (visualitzacio i validacio)

No formen part del pipeline principal, pero ajuden a provar i entendre resultats.

Jugar interactivament:

```bash
pixi run python src/play.py puzzles/sample1.json
```

Render d'imatge:

```bash
pixi run python src/image.py puzzles/sample1.json
```

Render GIF de la solucio:

```bash
pixi run python src/movie.py puzzles/2swap.json puzzles/2swap.sol.json
```

Visualitzacio 3D del graf:

```bash
pixi run python src/3D_view.py puzzles/2swap.graphml
pixi run python src/3D_view.py puzzles/2swap.graphml puzzles/2swap.sol.json
```

