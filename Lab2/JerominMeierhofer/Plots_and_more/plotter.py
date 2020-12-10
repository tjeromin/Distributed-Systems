import matplotlib.pyplot as plt
import numpy as np

round =  np.array([1, 2, 3, 4, 5])

latency40 =  np.array([22.3, 24.4, 32.8, 21.3, 24.5])
latency30 =  np.array([14.3, 13.2, 16.9, 13.8, 14.9])
latency20 =  np.array([6.0, 13.4, 8.0, 5.4, 8.5])
latency10 =  np.array([6.2, 7.3, 5.8, 6.9, 10.0])

plt.plot(round, latency40, label='40 requests')
plt.plot(round, latency30, label='30 requests')
plt.plot(round, latency20, label='20 requests')
plt.plot(round, latency10, label='10 requests')

plt.xlabel('round', fontsize=16)
plt.ylabel('latency (s)', fontsize=16)
plt.title('How Latency scales with requests (8 servers)')
plt.legend()
plt.show()


latency4 =  np.array([3.7, 7.5, 3.1, 4.1, 3.8])
latency8 =  np.array([6.2, 7.3, 5.8, 6.9, 10.0])

plt.plot(round, latency4, label='40 requests')
plt.plot(round, latency8, label='30 requests')

plt.xlabel('round', fontsize=16)
plt.ylabel('latency (s)', fontsize=16)
plt.title('How Latency scales with servers (10 concurrent requests)')
plt.legend()
plt.show()

latency_election = np.array([41.2, 39.8, 22.2, 28.8, 37.0])
plt.plot(round, latency_election)
plt.xlabel('round', fontsize=16)
plt.ylabel('latency (s)', fontsize=16)
plt.title('Election latency')
plt.show()