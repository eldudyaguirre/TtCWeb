import csv
from store.models import Categoria

def feed_categorias():
    Categoria.objects.all().delete()

    with open('data/categories.csv') as csv_file:
        csv_dict_reader = csv.DictReader(csv_file, delimiter=';')
        for item in csv_dict_reader:
            categoria = Categoria(nombre=item['name'],slug=item['slug'])
            categoria.save()
            print(f'Categoria creada: {categoria}')


def run():
    feed_categorias()