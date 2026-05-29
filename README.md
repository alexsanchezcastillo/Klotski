# Klotski AP2 — Memòria tècnica

Resolució de puzzles de peces lliscants modelant l'**espai d'estats** com a graf: construcció del graf, solució mínima, heurística d'interès (0–5 estrelles) i integració amb el repositori col·laboratiu. 


## Objectiu del projecte

- Construir el graf d'estats d'un puzzle Klotski.
- Trobar una solució mínima com a seqüència de moviments.
- Definir i justificar una heurística d'interès (0–5 estrelles) a partir de mètriques de `graph-tool`.
- Interactuar amb l'API: descarregar puzzles, enviar valoracions (`rate.py`), pujar puzzles nous (`upload.py`); generar candidats (`generate.py`).

## Estructura del projecte

El nostre projecte està composat pel README, els documents de la capreta source, els puzzles de la carpeta puzzles i els gifs de la carpeta img.

L'estructura del codi és la següent:

- [src/puzzle.py](src/puzzle.py), [src/logic.py](src/logic.py): model i moviments.
- [src/graph.py](src/graph.py): graf d'estats.
- [src/solve.py](src/solve.py): camí mínim → `.sol.json`.
- [src/eval.py](src/eval.py): mètriques + `score_terms` + `stars`.
- [src/rate.py](src/rate.py): POST de valoració a l'API.
- [src/download.py](src/download.py): descàrrega des del repositori.
- [src/generate.py](src/generate.py): generació aleatòria filtrada per `eval.py`.
- [src/upload.py](src/upload.py): penjar puzzles al web.
- [src/rate_all.py](src/rate_all.py): valorar diversos puzzles de l'API (tots).

També hi ha 3 puzzles generats pel nostre codi de nivell progressiu (el primer és el més fàcil). A més, a la carpeta img estan els 3 respectius gifs solucionant els puzzles. A continuació estan les comandes per visualitzar el graf associat i jugar els puzzles. 

```bash
pixi run python src/3D_view.py puzzles/puzzle1.graphml puzzles/puzzle1.sol.json
pixi run python src/play.py puzzles/puzzle1.json
```

## Desenvolupament cronològic

### Pas 0 - Preparació de l'entorn

Instal·lació de dependències i preparació de l'entorn de treball.

```bash
pixi install
```

### Pas 1 - download.py

Primer script implementat. Connecta amb l'API pública del repositori per obtenir la llista de puzzles disponibles i descarregar-los en format JSON. 

Comandes:

```bash
# Veure tots els identificadors
curl https://klotski.pauek.dev/api/puzzles

# Veure els primers 10 identificadors, formatats
curl -s https://klotski.pauek.dev/api/puzzles | jq '.[0:10]'

# Veure només el primer identificador
curl -s https://klotski.pauek.dev/api/puzzles | jq -r '.[0]'
```

```bash
# Descarregar el top complet (fins a 100)
pixi run python src/download.py

# Descarregar només N puzzles
pixi run python src/download.py --limit 10

# Descarregar un o diversos IDs concrets
pixi run python src/download.py --id <ID>
pixi run python src/download.py --id <ID1> --id <ID2>
```

### Pas 2 - graph.py

Segon script implementat. Construeix el graf d'estats accessibles des de l'estat inicial del puzzle.

Model utilitzat:
1. Node = un estat complet del puzzle (posició de totes les peces).
2. Aresta = un moviment vàlid d'un sol pas entre dos estats.
3. Exploració BFS des de l'estat inicial fins a esgotar tots els estats accessibles.

Sortida:
- Fitxer `.graphml` per cada puzzle (per defecte amb el mateix nom del `.json`).
- El graf guarda les dades dels nodes (`state`, `is_start`, `is_goal`) i el `puzzle` original.

Comandes:

```bash
# Crear el graf amb nom de sortida per defecte
pixi run python src/graph.py puzzles/puzzle1.json

# Crear el graf amb nom de sortida explícit
pixi run python src/graph.py puzzles/puzzle1.json puzzles/puzzle1.graphml
```

Nota de visualització: Obrir directament un `.graphml` al navegador mostra XML (text), no una imatge. Per veure el graf en 3D, cal executar el visor `3D_view.py`.

```bash
# Veure el graf sense camí de solució
pixi run python src/3D_view.py puzzles/puzzle1.graphml

# Veure el graf amb el camí de solució ressaltat (groc)
pixi run python src/3D_view.py puzzles/puzzle1.graphml puzzles/puzzle1.sol.json
```

### Pas 3 - solve.py

Tercer script implementat. Troba una solució mínima sobre el graf d'estats i la desa en format `.sol.json`.

Funcionalitat principal:
1. Carrega el puzzle i el `.graphml` associat o el genera si no existeix.
2. Busca el camí més curt des del node inicial fins a un node objectiu.
3. Converteix la seqüència d'estats a moviments `[peça, direcció]`.
4. Desa la solució en un fitxer `.sol.json`.

Comandes:

```bash
# Mode mínim: puzzle -> usa <puzzle>.graphml i desa <puzzle>.sol.json
pixi run python src/solve.py puzzles/puzzle1.json

# Indicant fitxer de graf explícit
pixi run python src/solve.py puzzles/puzzle1.json puzzles/puzzle1.graphml

# Indicant graf i nom de sortida de la solució
pixi run python src/solve.py puzzles/puzzle1.json puzzles/puzzle1.graphml puzzles/puzzle1.sol.json
```

Què es pot fer després de generar solució:
1. Visualització 3D del camí:

```bash
pixi run python src/3D_view.py puzzles/puzzle1.graphml puzzles/puzzle1.sol.json
```

2. Pel·lícula GIF:

```bash
pixi run python src/movie.py puzzles/puzzle1.json puzzles/puzzle1.sol.json img/puzzle1.gif
```

### Pas 4 - eval.py

Quart script implementat. Assigna **interès** entre **0 i 5 estrelles** (`stars`) a partir del graf d'estats. Alimenta `rate.py` i filtra candidats de `generate.py`.

Funcionalitat principal:

1. Carrega puzzle + `.graphml` (o el genera si no existeix; convenció: `foo.json` → `foo.graphml` al mateix directori).
2. `compute_metrics` — mètriques amb `graph-tool` (vegeu la secció Investigació més avall).
3. `compute_score_terms` — termes normalitzats L, P, K, R, S, C, D, T ∈ [0, 1].
4. `score_from_metrics` — combinació ponderada → `stars`.

#### Criteri d'«interès»

Combinació **subjectiva però explícita** de: densitat del camí (P), colls d'ampolla (K) i ramificació (R) com a factors principals; longitud de solució (L), mida del graf (S) i clustering (C) com a factors secundaris; penalitzacions per dead-ends (D) i puzzles massa petits o curts (T). Justificació visual: vegeu la secció Investigació més avall. Si `solvable` és fals → **stars = 0**.

Constants internes: `MIN_SOLUTION_SOFT = 3`, `MIN_NODES_SOFT = 12`, `OPTIMAL_AVG_DEGREE = 2.8`, `BETWEENNESS_NORM_FACTOR = 0.04`.

#### Mètriques del graf (`compute_metrics`)

| Mètrica | Descripció | En `stars` |
|---------|------------|------------|
| `solvable` | Objectiu accessible des de l'inicial | Prerequisit (si no, 0 estrelles) |
| `min_solution_len` | Moviments mínims fins a un objectiu; −1 si no resoluble | L |
| `path_density` | `min_solution_len / log10(nodes + 1)` | P |
| `nodes`, `edges` | Estats i transicions accessibles | S (via `nodes`) |
| `avg_degree` | Moviments possibles per estat (mitjana) | R |
| `dead_end_ratio` | Fracció d'estats amb un sol moviment (sense inici/objectiu) | D |
| `global_clustering` | Connexió local entre veïns (`graph-tool`) | C |
| `max_vertex_betweenness` | Coll d'ampolla en **estats** (camins que hi passen) | K |
| `max_edge_betweenness` | Coll d'ampolla en **moviments**; requereix `--with-betweenness` | No (informativa) |
| `connected_components` | Components connexes | Validació (habitualment 1) |

#### Termes de puntuació (0–1)

Tots els termes es limiten amb `clamp01(x) = min(1, max(0, x))`:

| Terme | Pes | Fórmula | Interpretació |
|-------|-----|---------|---------------|
| **L** | +5 % | `clamp(min_len/12) * clamp(min_len/3)` | Longitud de solució (pes baix) |
| **P** | +25 % | `clamp(path_density/1.7)` | El camí solució «ocupa» bé l'espai explorat |
| **K** | +25 % | `clamp(max_vertex_betweenness / max(1, 0.04*n))` | Coll d'ampolla clar (fases, ponts estrets) |
| **R** | +25 % | `clamp(1 - abs(avg_degree-2.8)/7.0)` | Ramificació al volt de 2.8 |
| **S** | +15 % | `clamp(log10(n+1)/1.0) * clamp(n/12)` | Mida del graf |
| **C** | +5 % | `clamp(global_clustering/0.06)` | Densitat local (secundari) |
| **D** | −10 % | `clamp(dead_end_ratio/2.50)` | Massa estats «passadís» |
| **T** | −5 % | `clamp(0.5*t_len + 0.5*t_size)` | Puzzle massa petit o fàcil (`t_len` si `min_len < 3`, `t_size` si `nodes < 12`) |

Combinació final:

```text
raw = 0.05*L + 0.25*P + 0.25*K + 0.25*R + 0.15*S + 0.05*C - 0.10*D - 0.05*T
raw = clamp(raw)
stars = 5 * raw
```

Sortida `--json`: mètriques, `score_terms`, `stars`. El flag `--with-betweenness` només afegeix `max_edge_betweenness` al JSON.

Comandes:

```bash
pixi run python src/eval.py puzzles/puzzle1.json
pixi run python src/eval.py puzzles/<id>.json --json
pixi run python src/eval.py puzzles/<id>.json --json --with-betweenness   # opcional
```

### Pas 5 - rate.py 

Cinquè script implementat. Envia una valoració (estrelles) d'un puzzle al repositori via API.

Funcionalitat principal:
1. Rep el fitxer `.json` del puzzle i el token d'autenticació.
2. Calcula la puntuació amb `eval.py` (mateixa fórmula que l'avaluació local).
3. Fa POST a `/api/puzzles/<id>/votes` amb `stars` en decimal (0.0–5.0, arrodonit a 2 decimals).

L'ID del puzzle és el nom del fitxer sense extensió. Si el fitxer ve de `download.py`, el nom ja és el hash SHA-256.

Comandes:

```bash
# Enviar vot
pixi run python src/rate.py puzzles/<id>.json --token <TOKEN>
```

### Pas 6 - generate.py

Genera puzzles aleatoris de qualitat usant un pipeline en dues fases per garantir eficiència i evitar penjades.

Flux:

1. Omple el taulell fins a ≥80% de cobertura → goal state dens (branching baix, solucions llargues).
2. BFS multi-font des del goal (màx. 30.000 nodes) → tria l'start en el top 20% de profunditat.
3. **Fase ràpida** (tots els candidats): BFS pur sense `graph-tool` → mètriques bàsiques + `fast_score`.
4. **Fase completa** (només el guanyador): `build_graph` (màx. 15.000 nodes) + `eval.py` per a la puntuació final.

La separació garanteix que la generació no es pengi mai, independentment de la mida de l'espai d'estats.

```bash
# Valors per defecte: 4×5, ≤12 peces, ≥80% cobertura
pixi run python src/generate.py --candidates 30 --min-stars 3 --out puzzles/nou.json

# Seed fixa per reproduir resultats
pixi run python src/generate.py --candidates 20 --seed 42

# Taulell més gran per a puzzles més difícils (solucions més llargues)
pixi run python src/generate.py --width 5 --height 5 --pieces 14 --min-stars 2.5
```

### Pas 7 - upload.py

Puja un puzzle generat al repositori col·laboratiu.

Funcionalitat principal:
1. Llegeix i valida el `.json` del puzzle (format canònic).
2. Calcula l'ID que li assignarà el servidor (SHA-256 del JSON compacte).
3. Fa `POST /api/puzzles` amb el puzzle i el token d'autenticació.

```bash
# Pujar un puzzle
pixi run python src/upload.py puzzles/generated_abc.json --token <TOKEN>

# Provar sense enviar
pixi run python src/upload.py puzzles/generated_abc.json --token <TOKEN> --dry-run

# Pujar i verificar que s'ha rebut correctament
pixi run python src/upload.py puzzles/generated_abc.json --token <TOKEN> --verify
```

Flux recomanat: `generate.py` → `eval.py` (comprovar qualitat) → `upload.py` → `rate.py` (enviar valoració).


### Pas 8 - rate_all.py 

Setè script implementat. Descarrega tots els puzzles del repositori, els avalua amb `eval.py` i envia totes les valoracions en una sola execució.

Funcionalitat principal:
1. Obté la llista d'IDs del repositori (`GET /api/puzzles`).
2. Per cada ID, usa el `.json` local si existeix; si no, el descarrega automàticament.
3. Construeix el `.graphml` si no existeix i calcula les estrelles amb `eval.py`.
4. Envia la valoració via `POST /api/puzzles/<id>/votes`.

Útil per mantenir el rànking actualitzat quan es millora la fórmula de puntuació: una sola crida sobreescriu totes les valoracions anteriors amb els nous valors.

Aquest script supera els minuts d'execució. Això és degut a que molts puzzles del top tenen grafs molt grans pels quals és impossible fer el BFS en un temps raoanable.

```bash
# Valorar tots els puzzles del repositori
pixi run python src/rate_all.py --token <TOKEN>

# Provar sense enviar (mostra les puntuacions calculades)
pixi run python src/rate_all.py --token <TOKEN> --dry-run

# Limitar a N puzzles
pixi run python src/rate_all.py --token <TOKEN> --limit 10
```

## Annex: justificació de la fórmula d'`eval.py`

Durant el desenvolupament vam revisar el catàleg de `graph-tool` (centralitats, components, camins mínims, clustering) i vam verificar visualment cada mètrica amb `3D_view.py` i `play.py`. A `eval.py` en fem servir només les funcions que van mostrar correlació clara amb la dificultat percebuda:

| Funció de `graph-tool` | Paper a la puntuació |
|------------------------|----------------------|
| `shortest_distance` | `min_solution_len`, `solvable`, `path_density` (termes L, P) |
| `betweenness` | `max_vertex_betweenness` (terme K); arestes només amb `--with-betweenness` |
| `global_clustering` | Terme C |
| `label_components` | Validació (`connected_components`; en el nostre flux sol ser 1) |

Altres funcions (`shortest_path`, `pagerank`, …) les vam considerar però no entren a la fórmula: `solve.py` ja resol el camí mínim i les centralitats alternatives no aportaven criteri clar davant la visualització 3D.

Verificació visual sobre puzzles de referència:

> Nota: `2swap` i `simplicity` són els puzzles d'exemple que s'ens van proporcionar per a que féssim proves. No s'inclouen a l'entrega però els citem aquí perquè il·lustren bé el comportament dels diferents termes de la fórmula.

| Puzzle | Sol. mínima | Observació visual | Efecte a `eval.py` |
|--------|-------------|-------------------|---------------------|
| `2swap` | 17 | Graf compacte, poc ramificat | P, R i S moderats |
| `puzzle1` | 29 | Camí llarg, reorganització intermèdia | P, K i R elevats |
| `simplicity` | 31 | Fases abans d'arribar a l'objectiu | P i K elevats si hi ha «pont» central |

| El que es veu al 3D | Terme / mètrica |
|--------------------|-----------------|
| Camí llarg en groc | P (principal), L secundari |
| «Pont» estret (estat obligatori) | K (`max_vertex_betweenness`) |
| Molts nodes | S |
| Graf lineal, passadissos | D ↑, C ↓ |
| Puzzle petit o solució curta | T ↑, L ↓ |
