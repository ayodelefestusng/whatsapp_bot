import importlib

for pkg in ('aiomysql','asyncmy','pymysql'):
    spec = importlib.util.find_spec(pkg)
    print(f"{pkg}: {'found' if spec else 'missing'}")
