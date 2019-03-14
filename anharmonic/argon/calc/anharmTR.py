#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
Created on Mon Mar 4 13:34:46 2019

@author: Ty Sterling
ty.sterling@colorado.edu

This code calculates the anharmonic phonon transmission across interfaces
in crystals. It uses force constants and velocities from MD simulations 
following the method in PHYSICAL REVIEW B 95, 115313 (2017)

UPDATE 03.13.2019: Including cutoff frequency to save time looping
"""

import numpy as np
import sys
import anharmFX as fx
import copy as cp
import scipy.linalg.blas as blas

##### SIMULATION PARAMETERS #####
dT = 6 #NEMD bath temperature difference

dtMD = 4.3e-15 #MD timestep
dn = 2**4 #frequency velocities are printed
dt = dtMD*dn #effective timestep for velocity data
steps = 2**20 #number of simulation steps

split = 2 #number of chunks to split data into for averaging
tn = (steps/dn/split) #number of steps per block of data
fcut = 2.15 #THz; use cutoff freq to save time computing Tr

win = 0.005 #gaussian smoothing width = THz
kb = 1.38063e-23 #Boltzmann's constant, J/K

forcefile = 'Fijk.dat'
velsfile = 'vels.compact.dat'
outfile = 'anh.tr.TEST.dat'

#####################################################################
#--------------------------------------------------------------------
#####################################################################
## Print parameters to screen
fx.printParams(dtMD,dt,dT,steps,split,tn,fcut)

## Get force constants from file 
fx.tic()
print('\tNow reading force constants from '+str(forcefile)+'\n')
#fijk, du, idsl, idsr, ids, nl, nr, n, = fx.readFijk(forcefile)
fx.toc()

## Generate time and freq. arrays
om, thz, dom = fx.makeTime(dt,tn)
fmax = np.argwhere(thz < fcut) #maximum frequency
fmin = np.argwhere(thz > -fcut) #minimum frequency
freq = np.intersect1d(fmax,fmin) #indicies of frequency points to cut off
nfreq = len(freq) #number of frequency points to check

## Read velocites 
with open(velsfile,'r') as fid:
    if int(fid.readline().strip().split()[1]) != n: #error checking
                sys.exit('LAMMPS ERROR: Numer of atoms in vels run doesn\'t'
                         'match forces run')
    if int(fid.readline().strip().split()[1]) != dn: #error checking
        sys.exit('LAMMPS ERROR: Different stride given in '
                 +str(velsfile))
    fid.readline() #skip comment
    for j in range(n): #read the ids for error checking
        if ids[j] != int(fid.readline().strip().split()[0]):
            sys.exit('LAMMPS ERROR: ids in '+str(velsfile)+' don\'t'
                 ' match'+str(forcefile))
    tmp = fid.readline() #skip comment
    
    ## Get velocities for each block
    for s in range(1):#split): #loop over blocks for averaging
        vels = np.zeros((tn,n*3)) # [time,(1vx,1vy,1vz,2vx,2vy,...)]
        print('\n\tNow reading velocities from block '+str(s+1)+'\n')                
        num = tn/10
        for j in range(tn): 
            if j != 0 and j%(num) == 0: #print progress updates
                print('\t\tNow '
                      +str(10*np.round(j/num,decimals=1))+
                      '% done reading block '+str(s+1))
            for k in range(n*3):
                vels[j,k] = float(fid.readline().strip().split()[0])
        fx.toc()
        
        ## Compute the spectral conductance terms
        print('\n\tNow computing anharmonic contributions for block '
              +str(s+1)+'\n')
        
        #############################################################
        vk = np.fft.fft(vels,axis=0)*dt
        vk = np.append(vk[tn/2:,:],vk[0:tn/2,:],axis=0)
        #(-freqmax,freqmax)
        
        #velocities of right atoms        
        vj = np.zeros((tn,nr*3)).astype(complex) 
        vj[:,0::3] = vk[:,idsr*3] #vx on right side
        vj[:,1::3] = vk[:,idsr*3+1] #vy on right side
        vj[:,2::3] = vk[:,idsr*3+2] #vz on right side
        
        #velocities of left atoms        
        vi = np.zeros((tn,nl*3)).astype(complex) 
        vi[:,0::3] = vk[:,idsl*3] #vx on left side
        vi[:,1::3] = vk[:,idsl*3+1] #vy on left side
        vi[:,2::3] = vk[:,idsl*3+2] #vz on left side
        
        qom = np.zeros((nfreq,nl*3)).astype(complex)
        for i in range(1):#nl) #loop over left atoms    
            if i != 0 and i%(nl/10) == 0: #print progress updates
                print('\t\tNow '+str(10*np.round(i/(nl/10),1))+'% done '
                      'comptuting spectral conductance for block '+str(s+1))
                    
            phix = np.asfortranarray(fijk[i*3,...]) #phi on i in x
            phiy = np.asfortranarray(fijk[i*3+1,...]) #phi on i in y
            phiz = np.asfortranarray(fijk[i*3+2,...]) #phi on i in z
            
            ##############################################################            
            vj = np.flipud(vj[freq,:]).conj() #(freqmax,-freqmax)
            vj = np.roll(vj,1,axis=0) #roll once to start at 0 in the loop
            vk = vk[freq,:].T #for dot product
            om = om[freq]
            omp = np.roll(np.flipud(om),1,axis=0) 
            for w in range(nfreq):
                if w != 0 and w%(nfreq/1000) == 0: #print progress updates
                    print('\t\tNow '+str(np.round(w/(nfreq/1000),1))+'% done '
                          'comptuting the etc term for block '+str(s+1))
                    fx.toc()
                    
                vj = np.roll(vj,-1,axis=0) #vj*(w-w')
                omp = np.roll(omp,-1,axis=0) #(w-w')
                
                for wp in range(nfreq): #loop over omega prime
                    if om[wp] == 0 or omp[wp] == 0: #divide by 0
                        qom[wp,i*3:i*3+2] = 0+0j
                    else: #dot product vj*_dot_kijk_dot_vk
                        qom[wp,i*3] = (blas.cgemm((1+0j),vj[wp,None], #x
                           blas.cgemm((1+0j),phix,vk[:,wp])))#/(om[wp]*omp[wp])) 
                        qom[wp,i*3+1] = (blas.cgemm((1+0j),vj[wp,None], #y
                           blas.cgemm((1+0j),phiy,vk[:,wp])))#/(om[wp]*omp[wp]))
                        qom[wp,i*3+2] = (blas.cgemm((1+0j),vj[wp,None], #z
                           blas.cgemm((1+0j),phiz,vk[:,wp])))#/(om[wp]*omp[wp]))
                        
                    
                
                
                
                
                
                
#                if w == 0:
#                    with open('w-wp.dat','w') as fid2:
#                        fid2.write(str(tn)+'\n--------------\n')
#                        for k in range(tn):
#                            fid2.write(str(thz[k])+'\n')
#                        fid2.write('---------------\n')
#                        for k in range(tn):
#                            fid2.write(str(tmpsum[k])+'\n')
#                        fid2.write('---------------\n')
#                else:
#                    with open('w-wp.dat','a') as fid2:
#                        for k in range(tn):
#                            fid2.write(str(tmpsum[k])+'\n')
#                        fid2.write('---------------\n')
                    
                
                        
        fx.toc()
    
            
                
            
            
    
    

