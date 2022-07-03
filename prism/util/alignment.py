import numpy as np
import heapq


def lazy_align(a,b,calign,cskip,return_cost=False):
	"""
	a generic implementation of the global alignment algorithm.

	this implementation is LAZY, and has linear best case performance,
	but falls back to the quadratic worst case time of the typical
	alignment algorithm if the things it is asked to align
	are very different.

	parameters:
		- a
			a sequence of elements

		- b
			another sequence of elements

		- calign
			a function that defines the
			cost of aligning two elements.
			
			must be nonnegative.

			e.g. lambda x,y: x!=y
			returns a cost of 1 for matching
			two elements that are not the same,
			and a cost of 0 for matching two elements
			that are the same.

		- cskip
			a function that defines the
			cost of skipping an element
			in an alignment.

			must be nonnegative.

			e.g. lambda x: len(x)
			defines the cost of skipping an
			element as the length of that 
			element.

		- return_cost
			optional parameter. if set
			to true, returns the cost 
			of the alignment.


	returns:
		an 'alignment', for example, here is an edit distance alignment between
		'smarts' with 'cat'

		```python
		[('s', 'c'), ('m', None), ('a', 'a'), ('r', None), ('t', 't'), ('s', None)]
		```
		
		what this alignment means, in order:
		1. misaligned 's' and 'c', incurring a penalty of 1.
		2. aligned 'm' in 'smart' with nothing in 'cat', incurring a penalty of 1.
		3. aligned 'a''s from both words. no penalty.
		4. aligned 'r' from 'smart' with nothing in 'cat'. penalty of 1.
		5. aligned 't''s from both words, finishing 'cat'.
		6. forced to align 's' from 'smarts' with nothing

		an alignment represents a transformation
		from one string to another incurring the
		minimum cost, where cost is defined
		by the functions given as arguments.

		it is a list of tuples whose first element
		is an element from the first sequence,
		and the second element is an element
		from the second sequence.

		elements may be None if the algorithm
		has decided to skip/insert an element.

		if return_cost is true,
		the algorithm returns a tuple
		of (incurred cost, alignment).

	"""
	# DP table
	D = np.zeros([len(a)+1,len(b)+1])+np.infty
	D[0,0]=0

	# backtracking table
	BT = np.zeros([len(a)+1,len(b)+1,2],dtype="int32")

	heap = [(0,0,0)]

	neighbors = np.array([[1,0],[1,1],[0,1]])

	cx,cy = None,None

	end = (len(a),len(b))

	glb = 0

	while (cx,cy)!=end:
		candidate = heapq.heappop(heap)
		# x,y are inverted so that heap properly tiebreaks.
		# we prefer things closer to the end.
		nc,cx,cy = candidate[0],-candidate[1],-candidate[2]
		costs = (
				cskip(a[cx]) if cx<len(a) else np.infty,
				calign(a[cx],b[cy]) if cx < len(a) and cy < len(b) else np.infty,
				cskip(b[cy]) if cy < len(b) else np.infty
		)


		for c,(x,y) in zip(costs,(cx,cy)+neighbors):
			# bounds check
			if (x>len(a) or y>len(b)):
				continue
			
			nc = c+D[cx,cy]
			if (nc < D[x,y]):
				D[x,y] = nc
				BT[x,y]=(cx,cy)
				heapq.heappush(heap,(nc, -x, -y))


	x,y = len(a),len(b)

	alignment = []

	while (x,y)!=(0,0):
		# backtrack once.
		nx,ny = BT[x,y]
		alignment.append((a[nx] if nx < x else None, b[ny] if ny < y else None))
		x,y = nx,ny
	

	if return_cost:
		return D[-1,-1],alignment[::-1]
	else:
		return alignment[::-1]




if __name__=="__main__":
	import random
	import sys

	# define edit distance using the alignment factory.
	edit_distance = lambda x,y: lazy_align(x,y,lambda x,y:x!=y,lambda x:1,return_cost=True)

	sys.stdout.write("testing alignment implementation")
	sys.stdout.flush()

	alpha = [chr(x) for x in range(ord('A'), ord('z')+1)]
	
	for _ in range(100):
		a = random.choices(alpha,k=1000)
		cost = random.randint(1,10)
		b = a.copy()
		for _ in range(cost):
			# pick a random index
			index = random.randint(0,len(b)-1)
			# and mutate that spot.
			if (random.random()>0.5):
				# delete the char
				del b[index]
			else:
				# change the char
				b[index] = 'a' if b[index]=='z' else 'z'
		cost_measured,alignment = edit_distance(a,b)

		# assert that the found alignment
		# is no worse than the mutations we caused.
		assert(cost>=cost_measured)

		a_recons,b_recons = list(zip(*alignment))
	
		# assert that a and b can be reconstructed
		# from the alignment.
		assert(list(filter(None,a_recons)) == a)
		assert(list(filter(None,b_recons)) == b)

		# assert that the cost is equal to sum
		# of errors in the alignment.
		
		assert(cost_measured==sum(x!=y for x,y in alignment))

		sys.stdout.write(".")
		sys.stdout.flush()

	print("alignment O.K.")
