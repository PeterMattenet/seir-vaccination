from seirsplus.models import *
from seirsplus.networks import *
from seirsplus.models_extra import *
import networkx
import math 

numNodes = 10000

baseGraph    = networkx.barabasi_albert_graph(n=numNodes, m=9)
baseGraph, cohortIndices, teamsIndices    = generate_workplace_contact_network(num_cohorts=10, num_nodes_per_cohort=1000, mean_intracohort_degree=9)

### Mandar escalas de distanciamiento social para precomputar los grafos por cada intensidad del protocolo de cuarentena (distancing_scales = [])
graphs, individualAgeBracketLabels, households    = generate_demographic_contact_network(N=numNodes, demographic_data=household_country_data("US"), verbose=False)

G_normal     = custom_exponential_graph(graphs['baseline'], scale=100)
# Social distancing interactions:
G_distancing = custom_exponential_graph(graphs['baseline'], scale=10)
# Quarantine interactions:
G_quarantine = custom_exponential_graph(graphs['baseline'], scale=5)

nodeGroups = {}
for index, age_bracket in enumerate(individualAgeBracketLabels):
    current_nodes = nodeGroups[age_bracket] if age_bracket in nodeGroups else []
    current_nodes.append(index)
    nodeGroups[age_bracket] = current_nodes

# model = VaccSEIRSNetworkModel(G=G_normal, beta=0.155, sigma=1/5.2, gamma=1/12.39, mu_I=0.0004, p=0.5,
#                           G_Q=G_quarantine, beta_Q=0.155, sigma_Q=1/5.2, gamma_Q=1/12.39, mu_Q=0.0004,
#                           theta_E=0.02, theta_I=0.02, phi_E=0.2, phi_I=0.2, psi_E=1.0, psi_I=1.0, q=0.5,
#                           initI=10)

model = VaccSEIRSNetworkModel(G=G_normal, beta=0.155, sigma=1/5.2, gamma=1/12.39, mu_I=0.0004, p=0.5,
                          G_Q=G_normal, beta_Q=0.155, sigma_Q=1/5.2, gamma_Q=1/12.39, mu_Q=0.0004,
                          theta_E=0.02, theta_I=0.02, phi_E=0.2, phi_I=0.2, psi_E=0, psi_I=0, q=0.5,
                          initI=10, node_groups=nodeGroups, v=0.0005, ve=0.9)
                          
checkpoints = {'t': [20, 100], 'G': [G_distancing, G_normal], 'p': [0.1, 0.5], 'theta_E': [0.02, 0.02], 'theta_I': [0.02, 0.02], 'phi_E':   [0.2, 0.2], 'phi_I':   [0.2, 0.2]}

# model.run(T=300, checkpoints=checkpoints, verbose=True)
model.run(T=200, verbose=True)

model.figure_infections(plot_E='stacked', plot_I='stacked', plot_V='line', plot_Q_I='stacked')
#model.figure_infections(plot_E='stacked', plot_I='stacked', plot_R='line', plot_Q_I='stacked')