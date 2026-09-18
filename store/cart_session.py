from store.models import Producto

CART_SESSION_ID = 'cart'

class ShoppingCartSession:

    """Inicializando el shopping cart"""
    def __init__(self, request):
        self.session = request.session
        cart = self.session.get(CART_SESSION_ID)
        if not cart:
            cart = self.session[CART_SESSION_ID] = {}
        self.cart = cart

    """Agregar item al cart"""
    def add(self, producto_id, cantidad=1):
        producto_id = str(producto_id)
        
        if producto_id not in self.cart:
            self.cart[producto_id] = cantidad
        else:
            self.cart[producto_id] += cantidad
        
        self.save()


    """Actualizar cantidad de item en el cart"""
    def update(self, producto_id, cantidad):
        producto_id = str(producto_id)

        if producto_id in self.cart:
            self.cart[producto_id] = cantidad
        
        self.save()


    """Quitar item del cart"""
    def delete(self, producto_id):
        producto_id = str(producto_id)

        if producto_id in self.cart:
            del self.cart[producto_id]            

        self.save()


    def save(self):
        self.session.modified = True
        

    def clear(self):
        del self.session[CART_SESSION_ID]


    """Contabilizar todas las unidades agregadas al carrito"""
    def __len__(self):
        return sum(self.cart.values())
    
    """Obtener el detalle de los productos que están en el carrito"""
    def get_cart_detail(self):
        cart_items = []
                
        for producto_id, cantidad in self.cart.items():
            producto = Producto.objects.get(pk=producto_id)
            cart_items.append({'producto': producto,
                               'cantidad': cantidad,
                               'subtotal': producto.precio * cantidad})
        return cart_items
    
    
    """Obtener el monto total de los items del carrito"""
    def get_total(self):        
        return sum(item['subtotal'] for item in self.get_cart_detail())