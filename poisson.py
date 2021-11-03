from seirsplus.networks import *
import networkx
import math 

#### Vamos a calcular el lambda para la distribución Poisson de Buenos Aires
valor_esperado = {}
diferencia_abs = 0
diferencia = 0
# Este valor surgio despues de iterar multiples veces a mano
lambda_poisson = 1.765

# Las estadisticas fueron provistas desde aca: https://www.estadisticaciudad.gob.ar/eyc/wp-content/uploads/2018/01/ir_2017_1223.pdf
# Como no proponen datos especificos para grupos familiares por encima de 5 miembros, para replicar el volumen de información provisto
# por el repositorio original con datos de Portland, Oregon (revisar), usamos una distribucion de Poisson para estimar los valores de grupos
# familiares de hasta 10 miembros. A partir de ese punto ya se puede considerar despreciable la probabilidad
tamaño_grupo_familiar = household_country_data("ARG")['household_size_distn']

# La justificacion por esto fue este articulo: https://www.researchgate.net/publication/226081704_Household_size_and_the_Poisson_distribution
# que argumenta en favor de usar esta distribucion como un buen aproximado del fenomeno que buscamos replicar. Utilizando los datos reales
# provistos por las estadisticas de la ciudad, con una heuristica simple se busco estimar el valor de tal manera que se minimice la diferencia entre
# los porcentajes medidos, y la distribucion propia. Se hayo un valor razonable donde para los primeros 5 valores de la distribucion, la diferencia absoluta
# llego a una suma de 0.03 (0.15 valor absoluto). Esta diferencia se vuelve menos significativa ya que el valor del lambda y la distribución Poisson se uso 
# para estimar las probabilidades del numero de personas en grupos familiares, solo para los valores de 5 para arriba, que en si representan solo 8% de la muestra total

for k in range(1, 5):
    valor_esperado[k] = (math.exp(-lambda_poisson) * math.pow(lambda_poisson, k) / math.factorial(k)) / (1 - math.exp(-lambda_poisson))
for i in range(1,5):
    diferencia_abs += abs(valor_esperado[i] - tamaño_grupo_familiar[i])
    diferencia += valor_esperado[i] - tamaño_grupo_familiar[i]
probabilidades_arriba_5 = 0
for k in range(5,11):
    probabilidades_arriba_5 += (math.exp(-lambda_poisson) * math.pow(lambda_poisson, k) / math.factorial(k)) / (1 - math.exp(-lambda_poisson))
diferencia_abs += abs(probabilidades_arriba_5 - tamaño_grupo_familiar[5])
diferencia += probabilidades_arriba_5 - tamaño_grupo_familiar[5]

### Binomial negativa truncada como alternativa
# https://www.jstor.org/stable/2333422?seq=1 para justificar la formula usada
def calcular_prob(personas):
    p = 1.16
    omega = 1 / (1 + p)
    nu = 1 - omega
    return (omega / (1 - omega)) * math.factorial(personas) * pow(nu, personas) / math.factorial(personas)
valor_esperado = {}
diferencia_abs = 0
diferencia = 0
k = 1
for k in range(1, 11):
    valor_esperado[k] = calcular_prob(k)
for i in range(1,5):
    diferencia_abs += abs(valor_esperado[i] - tamaño_grupo_familiar[i])
    diferencia += valor_esperado[i] - tamaño_grupo_familiar[i]
probabilidades_arriba_5 = 0 
for k in range(5,11):
    probabilidades_arriba_5 += calcular_prob(k)
diferencia_abs += abs(probabilidades_arriba_5 - tamaño_grupo_familiar[5])
diferencia += probabilidades_arriba_5 - tamaño_grupo_familiar[5]

print(probabilidades_arriba_5)
print(diferencia)
print(diferencia_abs)
print(valor_esperado)
exit()