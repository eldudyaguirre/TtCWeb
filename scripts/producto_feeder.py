import csv
from store.models import Producto, Categoria

def feed_productos():
    Producto.objects.all().delete()

    with open('data/products.csv') as csv_file:
        csv_dict_reader = csv.DictReader(csv_file, delimiter=';')
        for item in csv_dict_reader:
            producto = Producto(nombre=item['name'],
                                 descripcion=item['description'],
                                 precio=item['price'],
                                 imagen='imagenes/'+ item['image'],
                                 activo= (True if item['is_active']=='VERDADERO' else False)
                                 )
            producto.save()
            categoria = Categoria.objects.get(slug=item['category_slug'])
            producto.categorias.add(categoria)
            producto.save()
            print(f'Producto creado: {producto}')


def run():
    feed_productos()