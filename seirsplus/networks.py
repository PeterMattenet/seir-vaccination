from __future__ import division
import numpy
import scipy
import networkx
from . import FARZ
from .models import *

import matplotlib.pyplot as pyplot




def generate_workplace_contact_network(num_cohorts=1, num_nodes_per_cohort=100, num_teams_per_cohort=10,
                                        mean_intracohort_degree=6, pct_contacts_intercohort=0.2,
                                        farz_params={'alpha':5.0, 'gamma':5.0, 'beta':0.5, 'r':1, 'q':0.0, 'phi':10, 
                                                     'b':0, 'epsilon':1e-6, 'directed': False, 'weighted': False},
                                        distancing_scales=[]):

    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    # Generate FARZ networks of intra-cohort contacts:
    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    cohortNetworks = []

    teams_indices = {}

    for i in range(num_cohorts):

        numNodes            = num_nodes_per_cohort[i] if isinstance(num_nodes_per_cohort, list) else num_nodes_per_cohort
        numTeams            = num_teams_per_cohort[i] if isinstance(num_teams_per_cohort, list) else num_teams_per_cohort
        cohortMeanDegree    = mean_intracohort_degree[i] if isinstance(mean_intracohort_degree, list) else mean_intracohort_degree

        farz_params.update({'n':numNodes, 'k':numTeams, 'm':cohortMeanDegree})

        cohortNetwork, cohortTeamLabels = FARZ.generate(farz_params=farz_params)

        cohortNetworks.append(cohortNetwork)

        for node, teams in cohortTeamLabels.items():
            for team in teams:
                try:
                    teams_indices['c'+str(i)+'-t'+str(team)].append(node)
                except KeyError:
                    teams_indices['c'+str(i)+'-t'+str(team)] = [node]    

    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    # Establish inter-cohort contacts:
    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    cohortsAdjMatrices = [networkx.adj_matrix(cohortNetwork) for cohortNetwork in cohortNetworks]

    workplaceAdjMatrix = scipy.sparse.block_diag(cohortsAdjMatrices)
    workplaceNetwork   = networkx.from_scipy_sparse_matrix(workplaceAdjMatrix)

    N = workplaceNetwork.number_of_nodes()

    cohorts_indices = {}
    cohortStartIdx  = -1
    cohortFinalIdx  = -1
    for c, cohortNetwork in enumerate(cohortNetworks):

        cohortStartIdx = cohortFinalIdx + 1
        cohortFinalIdx = cohortStartIdx + cohortNetwork.number_of_nodes() - 1
        cohorts_indices['c'+str(c)] = list(range(cohortStartIdx, cohortFinalIdx))

        for team, indices in teams_indices.items():
            if('c'+str(c) in team):
                teams_indices[team] = [idx+cohortStartIdx for idx in indices]

        for i in list(range(cohortNetwork.number_of_nodes())):
            i_intraCohortDegree = cohortNetwork.degree[i]
            i_interCohortDegree = int( ((1/(1-pct_contacts_intercohort))*i_intraCohortDegree)-i_intraCohortDegree )
            # Add intercohort edges:
            if(len(cohortNetworks) > 1):
                for d in list(range(i_interCohortDegree)):
                    j = numpy.random.choice(list(range(0, cohortStartIdx))+list(range(cohortFinalIdx+1, N)))
                    workplaceNetwork.add_edge(i, j)

    return workplaceNetwork, cohorts_indices, teams_indices


# %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
# %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%


def generate_demographic_contact_network(N, demographic_data, layer_generator='FARZ', layer_info=None, distancing_scales=[], isolation_groups=[], verbose=False):

    graphs = {}

    age_distn               = demographic_data['age_distn']
    household_size_distn    = demographic_data['household_size_distn']
    household_stats         = demographic_data['household_stats']

    #########################################
    # Preprocess Demographic Statistics:
    #########################################

    ### Pedro: Calcular esperanza del tamaño de un hogar en funcion del diccionario 'household_size_distn' que almacena la probabilidad de cada numero
    meanHouseholdSize = numpy.average(list(household_size_distn.keys()), weights=list(household_size_distn.values()))
    # print("mean household size: " + str(meanHouseholdSize))

    # Calculate the distribution of household sizes given that the household has more than 1 member:
    ### Pedro: Calcular las probabilidades de que hayan X personas en un hogar sabiendo que hay mas de una persona. Esta probabilidad condicional se calcula dividiendo P(#H)IntersectP(#H>1) / P(#H>1),
    ### lo ultimo equivaliendo a 1 - P(#H = 1). Para H=1 simplemente lo definimos como 0, por mas que deberia reventar todo, peroo #JustPythonThings
    household_size_distn_givenGT1 = {key: value/(1-household_size_distn[1]) for key, value in household_size_distn.items()}
    household_size_distn_givenGT1[1] = 0

    ### Pedro: Calcular estos porcentajes con el paper de Portland Oregon. O pegarle un tubazo a Larreta y que me habilite un censo 2020
    # Percent of households with at least one member under 20:
    pctHouseholdsWithMember_U20          = household_stats['pct_with_under20']
    # Percent of households with at least one member over 60:
    pctHouseholdsWithMember_O60          = household_stats['pct_with_over60']
    # Percent of households with at least one member under 20 AND at least one over 60:
    pctHouseholdsWithMember_U20andO60    = household_stats['pct_with_under20_over60']
    # Percent of SINGLE OCCUPANT households where the occupant is over 60:
    pctHouseholdsWithMember_O60_givenEq1 = household_stats['pct_with_over60_givenSingleOccupant']
    # Average number of members Under 20 in households with at least one member Under 20:
    meanNumU20PerHousehold_givenU20      = household_stats['mean_num_under20_givenAtLeastOneUnder20']

    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    # Define major age groups (under 20, between 20-60, over 60), 
    # and calculate age distributions conditional on belonging (or not) to one of these groups:
    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    ### Pedro: Suponiendo que X pertenece a tal grupo demografico (<20, 20<y<60, 60<, 20<, <60), calcular la probabilidad de que pertenezca a cada bracket de diferencia de 10 años
    ### TO DO: Porque carajo esta distincion?
    ageBrackets_U20              = ['0-9', '10-19']
    totalPctU20                  = numpy.sum([age_distn[bracket] for bracket in ageBrackets_U20])
    age_distn_givenU20    = {bracket: pct/totalPctU20 for bracket, pct in age_distn.items() if bracket in ageBrackets_U20}

    ageBrackets_20to60           = ['20-29', '30-39', '40-49', '50-59']
    totalPct20to60               = numpy.sum([age_distn[bracket] for bracket in ageBrackets_20to60])
    age_distn_given20to60 = {bracket: pct/totalPct20to60 for bracket, pct in age_distn.items() if bracket in ageBrackets_20to60}

    ageBrackets_O60              = ['60-69', '70-79', '80+']
    totalPctO60                  = numpy.sum([age_distn[bracket] for bracket in ageBrackets_O60])
    age_distn_givenO60    = {bracket: pct/totalPctO60 for bracket, pct in age_distn.items() if bracket in ageBrackets_O60}

    ageBrackets_NOTU20           = ['20-29', '30-39', '40-49', '50-59', '60-69', '70-79', '80+']
    totalPctNOTU20               = numpy.sum([age_distn[bracket] for bracket in ageBrackets_NOTU20])
    age_distn_givenNOTU20 = {bracket: pct/totalPctNOTU20 for bracket, pct in age_distn.items() if bracket in ageBrackets_NOTU20}

    ageBrackets_NOTO60           = ['0-9', '10-19', '20-29', '30-39', '40-49', '50-59']
    totalPctNOTO60               = numpy.sum([age_distn[bracket] for bracket in ageBrackets_NOTO60])
    age_distn_givenNOTO60 = {bracket: pct/totalPctNOTO60 for bracket, pct in age_distn.items() if bracket in ageBrackets_NOTO60}


    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    # Calculate the probabilities of a household having members in the major age groups, 
    # conditional on single/multi-occupancy:
    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    ### Pedro: Probabilidades segmentadas tanto en cantidad de personas por hogar, como las edades que tienen. Las categorias son las siguientes:
    ###     - 1 integrante de tanto menos de 20 años como 60 (0 por las leyes de la fisica)
    ###     - 1 integrante menor de 20 años (0 por porcentaje despreciable)
    ###     - 1 integrante mayor de 60 años
    ###     - 1 integrante entre 20 y 60 años
    ###     - Al menos dos integrantes, uno menos de 20 y uno mas de 60
    ###     - Al menos dos integrantes, uno menos de 20 pero ninguno de mas de 60. Aclaracion, la formula incluye hogares con mas de un habitante, todos menores de 20, pero previamente se asume que es despreciable
    ###     - Al menos dos integrante, uno mayor de 60 pero ninguno menor de 20.
    ###     - Al menos dos integrantes, ninguno menor de 20 o mayor de 60
    prob_u20 = pctHouseholdsWithMember_U20    # probability of household having at least 1 member under 20
    prob_o60 = pctHouseholdsWithMember_O60    # probability of household having at least 1 member over 60
    prob_eq1 = household_size_distn[1]         # probability of household having 1 member
    prob_gt1 = 1 - prob_eq1                   # probability of household having greater than 1 member
    householdSituations_prob = {}    
    householdSituations_prob['u20_o60_eq1']       = 0     # can't have both someone under 20 and over 60 in a household with 1 member
    householdSituations_prob['u20_NOTo60_eq1']    = 0     # assume no one under 20 lives on their own (data suggests <1% actually do)
    householdSituations_prob['NOTu20_o60_eq1']    = pctHouseholdsWithMember_O60_givenEq1*prob_eq1
    householdSituations_prob['NOTu20_NOTo60_eq1'] = (1 - pctHouseholdsWithMember_O60_givenEq1)*prob_eq1
    householdSituations_prob['u20_o60_gt1']       = pctHouseholdsWithMember_U20andO60
    householdSituations_prob['u20_NOTo60_gt1']    = prob_u20 - householdSituations_prob['u20_o60_gt1'] - householdSituations_prob['u20_NOTo60_eq1'] - householdSituations_prob['u20_o60_eq1']
    householdSituations_prob['NOTu20_o60_gt1']    = prob_o60 - householdSituations_prob['u20_o60_gt1'] - householdSituations_prob['NOTu20_o60_eq1'] - householdSituations_prob['u20_o60_eq1']
    householdSituations_prob['NOTu20_NOTo60_gt1'] = prob_gt1 - householdSituations_prob['u20_o60_gt1'] - householdSituations_prob['NOTu20_o60_gt1'] - householdSituations_prob['u20_NOTo60_gt1']
    assert(numpy.sum(list(householdSituations_prob.values())) == 1.0), "Household situation probabilities must do not sum to 1" ### Macho, deberia sumar 1 en todo caso


    #########################################
    #########################################
    # Randomly construct households following the size and age distributions defined above:
    #########################################
    #########################################
    households     = []    # List of dicts storing household data structures and metadata
    homelessNodes  = N     # Number of individuals to place in households
    curMemberIndex = 0

    ### Pedro: Creame households a medida que gastas nodos huerfanos, usando primero las probabilidades para definir en que caso de la distribucion de edades entre integrantes cae.
    ### Una vez definido eso, a cada integrante, usando las distribucion demografica, asignarle un bracket de edad de 10 años
    while(homelessNodes > 0):
        
        household = {}

        household['situation'] = numpy.random.choice(list(householdSituations_prob.keys()), p=list(householdSituations_prob.values()))

        household['ageBrackets'] = []

        if(household['situation'] == 'NOTu20_o60_eq1'): 
            
            #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            # Household size is definitely 1
            household['size'] = 1

            #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            # There is only 1 member in this household, and they are OVER 60; add them:
            household['ageBrackets'].append( numpy.random.choice(list(age_distn_givenO60.keys()), p=list(age_distn_givenO60.values())) )
            
        elif(household['situation'] == 'NOTu20_NOTo60_eq1'):
            
            #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            # Household size is definitely 1
            household['size'] = 1
            
            # There is only 1 member in this household, and they are BETWEEN 20-60; add them:
            household['ageBrackets'].append( numpy.random.choice(list(age_distn_given20to60.keys()), p=list(age_distn_given20to60.values())) )
        
        elif(household['situation'] == 'u20_o60_gt1'):

            #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            # Draw a household size (given the situation, there's at least 2 members):
            household['size'] = min(homelessNodes, max(2, numpy.random.choice(list(household_size_distn_givenGT1), p=list(household_size_distn_givenGT1.values()))) )

            #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            # There's definitely at least one UNDER 20 in this household, add an appropriate age bracket:
            household['ageBrackets'].append( numpy.random.choice(list(age_distn_givenU20.keys()), p=list(age_distn_givenU20.values())) )
            # Figure out how many additional Under 20 to add given there is at least one U20; add them:
            # > Must leave room for at least one Over 60 (see minmax terms)
            numAdditionalU20_givenAtLeastOneU20 = min(max(0, numpy.random.poisson(meanNumU20PerHousehold_givenU20-1)), household['size']-len(household['ageBrackets'])-1)
            for k in range(numAdditionalU20_givenAtLeastOneU20):
                household['ageBrackets'].append( numpy.random.choice(list(age_distn_givenU20.keys()), p=list(age_distn_givenU20.values())) )

            #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            # There's definitely one OVER 60 in this household, add an appropriate age bracket:
            household['ageBrackets'].append( numpy.random.choice(list(age_distn_givenO60.keys()), p=list(age_distn_givenO60.values())) )
            
            #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            # Any remaining members can be any age EXCLUDING Under 20 (all U20s already added):
            for m in range(household['size'] - len(household['ageBrackets'])):
                household['ageBrackets'].append( numpy.random.choice(list(age_distn_givenNOTU20.keys()), p=list(age_distn_givenNOTU20.values())) )

        elif(household['situation'] == 'u20_NOTo60_gt1'): 

            #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            # Draw a household size (given the situation, there's at least 2 members):
            household['size'] = min(homelessNodes, max(2, numpy.random.choice(list(household_size_distn_givenGT1), p=list(household_size_distn_givenGT1.values()))) )

            #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            # There's definitely at least one UNDER 20 in this household, add an appropriate age bracket:
            household['ageBrackets'].append( numpy.random.choice(list(age_distn_givenU20.keys()), p=list(age_distn_givenU20.values())) )
            # Figure out how many additional Under 20 to add given there is at least one U20; add them:
            # > NOT CURRENTLY ASSUMING that there must be at least one non-Under20 member in every household (doing so makes total % U20 in households too low)

            numAdditionalU20_givenAtLeastOneU20 = min(max(0, numpy.random.poisson(meanNumU20PerHousehold_givenU20-1)), household['size']-len(household['ageBrackets']))
            for k in range(numAdditionalU20_givenAtLeastOneU20):
                household['ageBrackets'].append( numpy.random.choice(list(age_distn_givenU20.keys()), p=list(age_distn_givenU20.values())) )

            #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            # There are no OVER 60 in this household.

            #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            # Remaining members can be any age EXCLUDING OVER 60 and EXCLUDING UNDER 20 (all U20s already added):
            for m in range(household['size'] - len(household['ageBrackets'])):
                household['ageBrackets'].append( numpy.random.choice(list(age_distn_given20to60.keys()), p=list(age_distn_given20to60.values())) )

        elif(household['situation'] == 'NOTu20_o60_gt1'): 

            #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            # Draw a household size (given the situation, there's at least 2 members):
            household['size'] = min(homelessNodes, max(2, numpy.random.choice(list(household_size_distn_givenGT1), p=list(household_size_distn_givenGT1.values()))) )

            #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            # There are no UNDER 20 in this household.

            #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            # There's definitely one OVER 60 in this household, add an appropriate age bracket:
            household['ageBrackets'].append( numpy.random.choice(list(age_distn_givenO60.keys()), p=list(age_distn_givenO60.values())) )
            
            #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            # Any remaining members can be any age EXCLUDING UNDER 20:
            for m in range(household['size'] - len(household['ageBrackets'])):
                household['ageBrackets'].append( numpy.random.choice(list(age_distn_givenNOTU20.keys()), p=list(age_distn_givenNOTU20.values())) )

        elif(household['situation'] == 'NOTu20_NOTo60_gt1'):        
        
            #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            # Draw a household size (given the situation, there's at least 2 members):
            household['size'] = min(homelessNodes, max(2, numpy.random.choice(list(household_size_distn_givenGT1), p=list(household_size_distn_givenGT1.values()))) )

            #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            # There are no UNDER 20 in this household.

            #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            # There are no OVER 60 in this household.

            #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            # Remaining household members can be any age BETWEEN 20 TO 60, add as many as needed to meet the household size:
            for m in range(household['size'] - len(household['ageBrackets'])):
                household['ageBrackets'].append( numpy.random.choice(list(age_distn_given20to60.keys()), p=list(age_distn_given20to60.values())) )

        # elif(household['situation'] == 'u20_NOTo60_eq1'): 
        #    impossible by assumption
        # elif(household['situation'] == 'u20_o60_eq1'):    
        #    impossible

        if(len(household['ageBrackets']) == household['size']):

            homelessNodes -= household['size']

            households.append(household)

        else:
            print("Household size does not match number of age brackets assigned. "+household['situation'])


    numHouseholds = len(households)



    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    # Check the frequencies of constructed households against the target distributions:
    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    print("Generated overall age distribution:")
    for ageBracket in sorted(age_distn):
        age_freq = numpy.sum([len([age for age in household['ageBrackets'] if age==ageBracket]) for household in households])/N
        print(str(ageBracket)+": %.4f\t(%.4f from target)" % (age_freq, (age_freq - age_distn[ageBracket])) )
    print()

    print("Generated household size distribution:")
    for size in sorted(household_size_distn):
        size_freq = numpy.sum([1 for household in households if household['size']==size])/numHouseholds
        print(str(size)+": %.4f\t(%.4f from target)" % (size_freq, (size_freq - household_size_distn[size])) )
    print("Num households: " +str(numHouseholds))
    print("mean household size: " + str(meanHouseholdSize))
    print()
    
    if(verbose):
        print("Generated percent households with at least one member Under 20:")
        checkval = len([household for household in households if not set(household['ageBrackets']).isdisjoint(ageBrackets_U20)])/numHouseholds
        target   = pctHouseholdsWithMember_U20
        print("%.4f\t\t(%.4f from target)" % (checkval, checkval - target))
        
        print("Generated percent households with at least one Over 60")
        checkval = len([household for household in households if not set(household['ageBrackets']).isdisjoint(ageBrackets_O60)])/numHouseholds
        target   = pctHouseholdsWithMember_O60
        print("%.4f\t\t(%.4f from target)" % (checkval, checkval - target))
        
        print("Generated percent households with at least one Under 20 AND Over 60")
        checkval = len([household for household in households if not set(household['ageBrackets']).isdisjoint(ageBrackets_O60) and not set(household['ageBrackets']).isdisjoint(ageBrackets_U20)])/numHouseholds
        target   = pctHouseholdsWithMember_U20andO60
        print("%.4f\t\t(%.4f from target)" % (checkval, checkval - target))
        
        print("Generated percent households with 1 total member who is Over 60")
        checkval = numpy.sum([1 for household in households if household['size']==1 and not set(household['ageBrackets']).isdisjoint(ageBrackets_O60)])/numHouseholds
        target   = pctHouseholdsWithMember_O60_givenEq1*prob_eq1
        print("%.4f\t\t(%.4f from target)" % (checkval, checkval - target))

        print("Generated mean num members Under 20 given at least one member is Under 20")
        checkval = numpy.mean([numpy.in1d(household['ageBrackets'], ageBrackets_U20).sum() for household in households if not set(household['ageBrackets']).isdisjoint(ageBrackets_U20)])
        target   = meanNumU20PerHousehold_givenU20
        print("%.4f\t\t(%.4f from target)" % (checkval, checkval - target))

    #

    #########################################
    #########################################
    # Generate Contact Networks
    #########################################
    #########################################
    
    #########################################
    # Generate baseline (no intervention) contact network:
    #########################################

    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    # Define the age groups and desired mean degree for each graph layer:
    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    ### Pedro: Esta informacion se puede obtener del paper de portland? Este grado promedio representa conexiones intragrupo, o tanto intra como inter?
    if(layer_info is None):
        # Use the following default data if none is provided:
        # Data source: https://www.medrxiv.org/content/10.1101/2020.03.19.20039107v1
        layer_info  = { '0-9':   {'ageBrackets': ['0-9'],                   'meanDegree': 8.6, 'meanDegree_CI': (0.0, 17.7) },
                        '10-19': {'ageBrackets': ['10-19'],                 'meanDegree': 16.2, 'meanDegree_CI': (12.5, 19.8) },
                        '20-59': {'ageBrackets': ['20-29', '30-39', '40-49', '50-59'], 
                                                    'meanDegree': ((age_distn_given20to60['20-29']+age_distn_given20to60['30-39'])*15.3 + (age_distn_given20to60['40-49']+age_distn_given20to60['50-59'])*13.8), 
                                                    'meanDegree_CI': ( ((age_distn_given20to60['20-29']+age_distn_given20to60['30-39'])*12.6 + (age_distn_given20to60['40-49']+age_distn_given20to60['50-59'])*11.0), ((age_distn_given20to60['20-29']+age_distn_given20to60['30-39'])*17.9 + (age_distn_given20to60['40-49']+age_distn_given20to60['50-59'])*16.6) ) },
                        # '20-39': {'ageBrackets': ['20-29', '30-39'],        'meanDegree': 15.3, 'meanDegree_CI': (12.6, 17.9) },
                        # '40-59': {'ageBrackets': ['40-49', '50-59'],        'meanDegree': 13.8, 'meanDegree_CI': (11.0, 16.6) },
                        '60+':   {'ageBrackets': ['60-69', '70-79', '80+'], 'meanDegree': 13.9, 'meanDegree_CI': (7.3, 20.5) } }

    # Count the number of individuals in each age bracket in the generated households:
    ### Pedro: conta por la cantidad de individuos por bracket de edad en la totalidad de la red
    ageBrackets_numInPop = {ageBracket: numpy.sum([len([age for age in household['ageBrackets'] if age==ageBracket]) for household in households])
                            for ageBracket, __ in age_distn.items()}

    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    # Generate a graph layer for each age group, representing the public contacts for each age group:
    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    adjMatrices           = []
    adjMatrices_isolation_mask = []

    individualAgeGroupLabels = []

    curidx = 0
    ### Pedro: iterar por las layers, definidas como grupos etarios de 0-9, 10-19, 20-59, 60+. Esta layer info tiene que agrupar brackets etarios pasados en la AgeDistribution al principio del codigo
    ### Estan restringidas por la calidad de la informacion en cuanto a: la cantidad de conexiones que cada nodo en un rango etario tiene (esperanza e intervalo de confianza)
    for layerGroup, layerInfo in layer_info.items():
        print("Generating graph for "+layerGroup+"...")
        
        layerInfo['numIndividuals'] = numpy.sum([ageBrackets_numInPop[ageBracket] for ageBracket in layerInfo['ageBrackets']])

        layerInfo['indices']        = range(curidx, curidx+layerInfo['numIndividuals'])
        curidx                      += layerInfo['numIndividuals']


        ### Pedro: esta monstruosidad se traduce a, para el arreglo de grupos etarios por cada nodo del grafo final, asignarle la etiqueta de edad definida por LAYER_INFO, no AGE_DISTRIBUTION
        individualAgeGroupLabels[min(layerInfo['indices']):max(layerInfo['indices'])] = [layerGroup]*layerInfo['numIndividuals']

        graph_generated = False
        graph_gen_attempts = 0

        # Note, we generate a graph with average_degree parameter = target mean degree - meanHousehold size
        # so that when in-household edges are added each graph's mean degree will be close to the target mean
        targetMeanDegree = layerInfo['meanDegree']-int(meanHouseholdSize)

        targetMeanDegreeRange = (targetMeanDegree+meanHouseholdSize-0.75, targetMeanDegree+meanHouseholdSize+0.75) if layer_generator=='FARZ' else layerInfo['meanDegree_CI']
        # targetMeanDegreeRange = (targetMeanDegree+meanHouseholdSize-1, targetMeanDegree+meanHouseholdSize+1)

        while(not graph_generated):
            try:
                if(layer_generator == 'LFR'):

                    # print "TARGET MEAN DEGREE     = " + str(targetMeanDegree)
                
                    layerInfo['graph'] = networkx.generators.community.LFR_benchmark_graph(
                                            n=layerInfo['numIndividuals'], 
                                            tau1=3, tau2=2, mu=0.5, 
                                            average_degree=int(targetMeanDegree), 
                                            tol=1e-01, max_iters=200, seed=(None if graph_gen_attempts<10 else int(numpy.random.rand()*1000)))

                elif(layer_generator == 'FARZ'):

                    # https://github.com/rabbanyk/FARZ
                    ### Pedro: Explicame porque el grado esta dividido por dos? Edit: el codigo robado de FARZ toma el parametro m como HALF the averange number of nodes...
                    ### Explicame como le justifico estos parametros a Feuer.

                    ### Por lo visto, el modulo de FARZ genera una red que esta segmentada en comunidades. Cada una de estas redes representa una franja etaria de LAYER_INFO, 
                    ### pero no se cual es el criterio para particionar la red de tal forma. Habra que leer la docu de FARZ para entender el criterio de clustering que se usa.
                    ### - Estimo que esto es en plan de unir a los grupos demograficos entre si, sin contar las conexiones entre Household/Grupo familiar
                    ### - Separacion entre grupos sociales, comunidades de grupos que comparten la edad entre si. Amistades
                    layerInfo['graph'], layerInfo['communities'] = FARZ.generate(farz_params={ 
                                                                    'n': layerInfo['numIndividuals'], 
                                                                    'm': int(targetMeanDegree/2), # mean degree / 2
                                                                    'k': int(layerInfo['numIndividuals']/50), # num communities
                                                                    'alpha': 2.0,                 # clustering param
                                                                    'gamma': -0.6,                 # assortativity param
                                                                    'beta':  0.6,                 # prob within community edges
                                                                    'r':     1,                  # max num communities node can be part of
                                                                    'q':     0.5,                 # probability of multi-community membership
                                                                    'phi': 1, 'b': 0.0, 'epsilon': 0.0000001, 
                                                                    'directed': False, 'weighted': False})

                elif(layer_generator == 'BA'):
                    pass

                else:
                    print("Layer generator \""+layer_generator+"\" is not recognized (support for 'LFR', 'FARZ', 'BA'")
                
                nodeDegrees = [d[1] for d in layerInfo['graph'].degree()]
                meanDegree  = numpy.mean(nodeDegrees)
                maxDegree   = numpy.max(nodeDegrees)

                # Enforce that the generated graph has mean degree within the 95% CI of the mean for this group in the data:
                ### Pedro: Obliga a que el grado promedio de la red FARZ (volver a sumar el tamaño promedio de Grupo Familiar) se encuentre adentro del intervalo de confianza
                if(meanDegree+meanHouseholdSize >= targetMeanDegreeRange[0] and meanDegree+meanHouseholdSize <= targetMeanDegreeRange[1]):
                # if(meanDegree+meanHouseholdSize >= targetMeanDegree+meanHouseholdSize-1 and meanDegree+meanHouseholdSize <= targetMeanDegree+meanHouseholdSize+1):
            
                    if(verbose):
                        print(layerGroup+" public mean degree = "+str((meanDegree)))
                        print(layerGroup+" public max degree  = "+str((maxDegree)))

                    ### Pedro: Guardar la matriz de adyacencia del grafo generado
                    adjMatrices.append(networkx.adj_matrix(layerInfo['graph']))

                    # Create an adjacency matrix mask that will zero out all public edges
                    # for any isolation groups but allow all public edges for other groups:
                    ### Pedro: Si la red es de aislamiento (aislar por grupo etario es un buen caso de prueba) entonces guardar una mascara de 0s para evitar aristas que salgan de este grupo
                    if(layerGroup in isolation_groups):
                        adjMatrices_isolation_mask.append(numpy.zeros(shape=networkx.adj_matrix(layerInfo['graph']).shape))
                    else:
                        # adjMatrices_isolation_mask.append(numpy.ones(shape=networkx.adj_matrix(layerInfo['graph']).shape))
                        # The graph layer we just created represents the baseline (no dist) public connections;
                        # this should be the superset of all connections that exist in any modification of the network,
                        # therefore it should work to use this baseline adj matrix as the mask instead of a block of 1s 
                        # (which uses unnecessary memory to store a whole block of 1s, ie not sparse)
                        adjMatrices_isolation_mask.append(networkx.adj_matrix(layerInfo['graph']))

                    graph_generated = True

                else:
                    graph_gen_attempts += 1
                    if(graph_gen_attempts >= 1):# and graph_gen_attempts % 2):
                        if(meanDegree+meanHouseholdSize < targetMeanDegreeRange[0]):
                            targetMeanDegree += 1 if layer_generator=='FARZ' else 0.05
                        elif(meanDegree+meanHouseholdSize > targetMeanDegreeRange[1]):
                            targetMeanDegree -= 1 if layer_generator=='FARZ' else 0.05
                        # reload(networkx)
                    if(verbose):
                        # print("Try again... (mean degree = "+str(meanDegree)+"+"+str(meanHouseholdSize)+" is outside the target range for mean degree "+str(targetMeanDegreeRange)+")")
                        print("\tTry again... (mean degree = %.2f+%.2f=%.2f is outside the target range for mean degree (%.2f, %.2f)" % (meanDegree, meanHouseholdSize, meanDegree+meanHouseholdSize, targetMeanDegreeRange[0], targetMeanDegreeRange[1]))
            
            # The networks LFR graph generator function has unreliable convergence.
            # If it fails to converge in allotted iterations, try again to generate.
            # If it is stuck (for some reason) and failing many times, reload networkx.
            except networkx.exception.ExceededMaxIterations:
                graph_gen_attempts += 1
                # if(graph_gen_attempts >= 10 and graph_gen_attempts % 10):
                #     reload(networkx)
                if(verbose):
                    print("\tTry again... (networkx failed to converge on a graph)")

    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    # Assemble an graph for the full population out of the adjacencies generated for each layer:
    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    ### Pedro: no se como funciona esta magia y no voy a averiguarlo hoy. No parece haber intento de crear conexiones entre grupos etarios mas alla de los grupos familiares
    A_baseline = scipy.sparse.lil_matrix(scipy.sparse.block_diag(adjMatrices))
    # Create a networkx Graph object from the adjacency matrix:
    G_baseline = networkx.from_scipy_sparse_matrix(A_baseline)
    graphs['baseline'] = G_baseline


    #########################################
    # Generate social distancing modifications to the baseline *public* contact network:
    #########################################
    # In-household connections are assumed to be unaffected by social distancing, 
    # and edges will be added to strongly connect households below.
    
    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    # Social distancing graphs are generated by randomly drawing (from an exponential distribution) 
    # a number of edges for each node to *keep*, and other edges are removed.
    #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    G_baseline_NODIST   = graphs['baseline'].copy()
    # Social distancing interactions:
    ### Pedro: Generar multiples grafos por cada intensidad del distanciamiento social llamando a custom_exponential_graph
    for dist_scale in distancing_scales:
        graphs['distancingScale'+str(dist_scale)] = custom_exponential_graph(G_baseline_NODIST, scale=dist_scale)
        if(verbose):
            nodeDegrees_baseline_public_DIST    = [d[1] for d in graphs['distancingScale'+str(dist_scale)].degree()]
            print("Distancing Public Degree Pcts:")
            (unique, counts) = numpy.unique(nodeDegrees_baseline_public_DIST, return_counts=True)
            print([str(unique)+": "+str(count/N) for (unique, count) in zip(unique, counts)])
            # pyplot.hist(nodeDegrees_baseline_public_NODIST, bins=range(int(max(nodeDegrees_baseline_public_NODIST))), alpha=0.5, color='tab:blue', label='Public Contacts (no dist)')
            pyplot.hist(nodeDegrees_baseline_public_DIST, bins=range(int(max(nodeDegrees_baseline_public_DIST))), alpha=0.5, color='tab:purple', label='Public Contacts (distancingScale'+str(dist_scale)+')')
            pyplot.xlim(0,40)
            pyplot.xlabel('degree')
            pyplot.ylabel('num nodes')
            pyplot.legend(loc='upper right')
            pyplot.show()


    #########################################
    # Generate modifications to the contact network representing isolation of individuals in specified groups:
    #########################################
    ### Pedro: aplicar mascaras de cada red aislada. Aunque, no entiendo realmente en que momento se unificaron los diversos grafos FARZ
    if(len(isolation_groups) > 0):
    
        #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        # Assemble an adjacency matrix mask (from layer generation step) that will zero out 
        # all public contact edges for the isolation groups but allow all public edges for other groups. 
        #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        A_isolation_mask    = scipy.sparse.lil_matrix(scipy.sparse.block_diag(adjMatrices_isolation_mask))

        #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        # Then multiply each distancing graph by this mask to generate the corresponding 
        # distancing adjacency matrices where the isolation groups are isolated (no public edges),
        # and create graphs corresponding to the isolation intervention for each distancing level:
        #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        for graphName, graph in graphs.items():
            A_withIsolation = scipy.sparse.csr_matrix.multiply( networkx.adj_matrix(graph), A_isolation_mask )
            graphs[graphName+'_isolation'] = networkx.from_scipy_sparse_matrix(A_withIsolation)

    

    #########################################
    #########################################
    # Add edges between housemates to strongly connect households:
    #########################################
    #########################################
    # Apply to all distancing graphs

    # Create a copy of the list of node indices for each age group (graph layer) to draw from:
    for layerGroup, layerInfo in layer_info.items():
        layerInfo['selection_indices'] = list(layerInfo['indices'])

    individualAgeBracketLabels = [None]*N

    # Go through each household, look up what the age brackets of the members should be,
    # and randomly select nodes from corresponding age groups (graph layers) to place in the given household.
    # Strongly connect the nodes selected for each household by adding edges to the adjacency matrix.
    ### Pedro: al final, una vez hecho la multiplicacion de matrices de aislamiento, crear aristas que unan a todos los miembros del grupo familiar, creando una subred fuertemente conectada
    for household in households:
        household['indices'] = []
        for ageBracket in household['ageBrackets']:
            ageGroupIndices = next(layer_info[item]['selection_indices'] for item in layer_info if ageBracket in layer_info[item]["ageBrackets"])
            memberIndex     = ageGroupIndices.pop()
            household['indices'].append(memberIndex)

            individualAgeBracketLabels[memberIndex] = ageBracket

        for memberIdx in household['indices']:
            nonselfIndices = [i for i in household['indices'] if memberIdx!=i]
            for housemateIdx in nonselfIndices:
                # Apply to all distancing graphs
                for graphName, graph in graphs.items():
                    graph.add_edge(memberIdx, housemateIdx)


    #########################################
    # Check the connectivity of the fully constructed contacts graphs for each age group's layer:
    #########################################
    if(verbose):
        for graphName, graph in graphs.items():
            nodeDegrees    = [d[1] for d in graph.degree()]
            meanDegree= numpy.mean(nodeDegrees)
            maxDegree= numpy.max(nodeDegrees)
            components = sorted(networkx.connected_components(graph), key=len, reverse=True)
            numConnectedComps = len(components)
            largestConnectedComp = graph.subgraph(components[0])
            print(graphName+": Overall mean degree = "+str((meanDegree)))
            print(graphName+": Overall max degree = "+str((maxDegree)))
            print(graphName+": number of connected components = {0:d}".format(numConnectedComps))
            print(graphName+": largest connected component = {0:d}".format(len(largestConnectedComp)))
            for layerGroup, layerInfo in layer_info.items():
                nodeDegrees_group = networkx.adj_matrix(graph)[min(layerInfo['indices']):max(layerInfo['indices']), :].sum(axis=1)
                print("\t"+graphName+": "+layerGroup+" final graph mean degree = "+str(numpy.mean(nodeDegrees_group)))
                print("\t"+graphName+": "+layerGroup+" final graph max degree  = "+str(numpy.max(nodeDegrees_group)))
                pyplot.hist(nodeDegrees_group, bins=range(int(max(nodeDegrees_group))), alpha=0.5, label=layerGroup)
            # pyplot.hist(nodeDegrees, bins=range(int(max(nodeDegrees))), alpha=0.5, color='black', label=graphName)
            pyplot.xlim(0,40)
            pyplot.xlabel('degree')
            pyplot.ylabel('num nodes')
            pyplot.legend(loc='upper right')
            pyplot.show()

    #########################################

    return graphs, individualAgeBracketLabels, households


def household_country_data(country):

    if(country=='US'):
        household_data = {
                            'household_size_distn':{ 1: 0.283708848, 
                                                    2: 0.345103011, 
                                                    3: 0.150677793,
                                                    4: 0.127649150, 
                                                    5: 0.057777709, 
                                                    6: 0.022624223, 
                                                    7: 0.012459266  },

                            'age_distn':{'0-9':   0.121,
                                                '10-19': 0.131,
                                                '20-29': 0.137,
                                                '30-39': 0.133,
                                                '40-49': 0.124,
                                                '50-59': 0.131,
                                                '60-69': 0.115,
                                                '70-79': 0.070,
                                                '80+'  : 0.038  },

                            'household_stats':{ 'pct_with_under20':          0.3368, 
                                                'pct_with_over60':           0.3801,
                                                'pct_with_under20_over60':  0.0341,
                                                'pct_with_over60_givenSingleOccupant':       0.110,
                                                'mean_num_under20_givenAtLeastOneUnder20':  1.91 }
                        }
    if(country=='ARG'):
        household_data = {
            # Uso de distribuicion Poisson para estimar los grupos familiares de 5 para arriba, usando una distribucion Poisson(1.765) para reflejar cuantos familiares adicionales a 5 hay
            # Esto es una
            'household_size_distn':{ 1: 0.365, 
                                        2: 0.258, 
                                        3: 0.158,
                                        4: 0.139, 
                                        5: 0.02948192762642533,
                                        6: 0.00867260037677345,
                                        7: 0.002186734237857877, 
                                        8: 0.00048244824122739403, 
                                        9: 9.461346064070563e-05, 
                                        10: 1.669927580308454e-05,
                                    },

            'age_distn':{'0-4':   0.057311,
                            '5-9': 0.054105,
                            '10-14': 0.052074,
                            '15-19': 0.058018,
                            '20-24': 0.078932,
                            '25-29': 0.085668,
                            '30-34': 0.085833,
                            '35-39': 0.074503,
                            '40-44': 0.062584,
                            '45-49': 0.059383,
                            '50-54': 0.059174,
                            '55-59': 0.055753,
                            '60-64': 0.052632,
                            '65-69': 0.044432,
                            '70-74': 0.036390,
                            '75-79': 0.032281,
                            '80-84': 0.027012,
                            '85-89': 0.016123,
                            '90+': 0.007791 },

            # el Primero podria calculandolo viendo la cantidad de menores de 20 que hay censado, el promedio de jovenes por casa y asi estimar cuantas casas tienen jovenes del total
            # este podria calcularlo con la cantidad de hogares donde vive un anciano solo, un anciano con su pareja, y despues asumir que el resto habitan 1 por vivienda y no es compartida (hmm no se)
            # hmm ni idea (censo hogares compartidos por familia entera extendida)
            # ya esta calculado, contamos los ancianos y con el porcentaje de uno de los censos sabemos cuantas viviendas estan ocupadas por uno solo, eso habria que dividirlo por cuantas casas son de un unico habitante
            # tenemos el promedio de jovenes entre 15-29
            #    https://www.estadisticaciudad.gob.ar/eyc/publicaciones/situacion_jovenes_caba_2019/#:~:text=En%20un%20tercio%20(32%2C3,6%25%20est%C3%A1%20encabezado%20por%20j%C3%B3venes.&text=El%2015%2C5%25%20de%20los%20j%C3%B3venes%20viven%20solos.
            #
            'household_stats':{ 'pct_with_under20':          0.3368, 
                                'pct_with_over60':           0.3801,
                                'pct_with_under20_over60':  0.0341,
                                'pct_with_under25_givenSingleOccupant':  0.36801,
                                'pct_with_over65_givenSingleOccupant':  0.36801,
                                'mean_num_under20_givenAtLeastOneUnder20':  1.91,
                                'pct_with_over15_under30':  0.2 }

            # OK, nueva propuesta. Primero elegir al azar que tipo de jefe va a manejar la casa. Luego determinar cuantos habitantes van a ocuparla 
            #   En el caso de jefe de 65 ya calculamos las chances de que viva solo, o en pareja (2), o resto de familia extendida + otros
            #       https://www.estadisticaciudad.gob.ar/eyc/wp-content/uploads/2017/05/DP60SC.xlsx
            #   En el caso de jovenes, habria que ver
            #   https://www.estadisticaciudad.gob.ar/eyc/wp-content/uploads/2015/04/ir_2012_492.pdf pero es del 2010, nos permite para toda edad saber las chances de que viva solo
            #   El resto de las franjas podriamos tratar las probabilidades de household tal como estan planteadas
            # Una vez definido el numero de habitantes, calculamos la probabilidad por caso de jefe de que un nuevo habitante sea de que franja etaria
            #   Para esto poddriamos simplemente tratarlo como una variable aleatoria donde las chances de X edad es igual a #GenteDeEsaEdadQueHabitaConJefeY / #GEnteQueHabitaConJefeY 
            #   Recordar no contar a la gente que YA es jefe
            #   Alternativa, usar la media y, con eso definir una poisson por cada edad? Iterar hasta que se llene el cupo de la casa? No tiene mucho sentido
            #   Si se da que el jefe es mayor de 24, y hay un crio, podemos agregar los hermanos a partir de una Poisson con promedio 1.54
            #       https://www.estadisticaciudad.gob.ar/eyc/wp-content/uploads/2019/01/ir_2019_1334.pdf
            # Una vez tomada esta nueva persona, usar las probabilidades demografias para restringir a que edad pertenece, adentro de su sub grupo


        }
    return household_data

#%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
#%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%


#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Defines a random exponential edge pruning mechanism   
# where the mean degree be easily down-shifted
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
def custom_exponential_graph(base_graph=None, scale=100, min_num_edges=0, m=9, n=None):
    # If no base graph is provided, generate a random preferential attachment power law graph as a starting point.
    if(base_graph):
        graph = base_graph.copy()
    else:
        assert(n is not None), "Argument n (number of nodes) must be provided when no base graph is given."
        graph = networkx.barabasi_albert_graph(n=n, m=m)

    # We modify the graph by probabilistically dropping some edges from each node. 
    for node in graph:
        neighbors = list(graph[node].keys())
        if(len(neighbors) > 0):
            quarantineEdgeNum = int( max(min(numpy.random.exponential(scale=scale, size=1), len(neighbors)), min_num_edges) )
            quarantineKeepNeighbors = numpy.random.choice(neighbors, size=quarantineEdgeNum, replace=False)
            for neighbor in neighbors:
                if(neighbor not in quarantineKeepNeighbors):
                    graph.remove_edge(node, neighbor)
    
    return graph

#^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
#^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

def plot_degree_distn(graph, max_degree=None, show=True, use_seaborn=True):
    import matplotlib.pyplot as pyplot
    if(use_seaborn):
        import seaborn
        seaborn.set_style('ticks')
        seaborn.despine()
    # Get a list of the node degrees:
    if type(graph)==numpy.ndarray:
        nodeDegrees = graph.sum(axis=0).reshape((graph.shape[0],1))   # sums of adj matrix cols
    elif type(graph)==networkx.classes.graph.Graph:
        nodeDegrees = [d[1] for d in graph.degree()]
    else:
        raise BaseException("Input an adjacency matrix or networkx object only.")
    # Calculate the mean degree:
    meanDegree = numpy.mean(nodeDegrees)
    # Generate a histogram of the node degrees:
    pyplot.hist(nodeDegrees, bins=range(max(nodeDegrees)), alpha=0.75, color='tab:blue', label=('mean degree = %.1f' % meanDegree))
    pyplot.xlim(0, max(nodeDegrees) if not max_degree else max_degree)
    pyplot.xlabel('degree')
    pyplot.ylabel('num nodes')
    pyplot.legend(loc='upper right')
    if(show):
        pyplot.show()













