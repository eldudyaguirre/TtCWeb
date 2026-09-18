from store.models import Categoria
from .cart_session import ShoppingCartSession

def get_all_categorias(request):
    categorias = Categoria.objects.all()
    return {'categorias': categorias}


def get_count_shopping_cart_items(request):
    cart = ShoppingCartSession(request)    
    count_cart_items = cart.__len__()
    return {'count_cart_items': count_cart_items}