import matplotlib.pyplot as plt
import numpy as np

def calc_avg(list):
    avg = 0
    for i in list:
        avg += i
    return avg / len(list)


round =  np.array([1, 2, 3, 4, 5])

latency40 =  np.array([4.0, 18.4, 12.8, 11.8, 9.2])
latency30 =  np.array([10.2, 11.2, 4.3, 10.1, 11.0])
latency20 =  np.array([3.4, 3.1, 3.4, 3.2, 3.5])
latency10 =  np.array([3.4, 2.9, 3.6, 3.1, 3.2])

print("%.2f" % calc_avg(latency40))
print("%.2f" % np.std(latency40))

plt.plot(round, latency40, label='40 requests' + ' avg: ' + ("%.2f" % calc_avg(latency40)) + ' std: ' + ("%.2f" % np.std(latency40)))
plt.plot(round, latency30, label='30 requests' + ' avg: ' + ("%.2f" % calc_avg(latency30)) + ' std: ' + ("%.2f" % np.std(latency30)))
plt.plot(round, latency20, label='20 requests' + ' avg: ' + ("%.2f" % calc_avg(latency20)) + ' std: ' + ("%.2f" % np.std(latency20)))
plt.plot(round, latency10, label='10 requests' + ' avg: ' + ("%.2f" % calc_avg(latency10)) + ' std: ' + ("%.2f" % np.std(latency10)))

plt.xlabel('round', fontsize=16)
plt.ylabel('latency (s)', fontsize=16)
plt.title('How Latency scales with requests (8 servers)')
plt.legend()
plt.show()

latency_reunion8 = np.array([10.4, 6.4, 7.1, 7.9, 4.8])
latency_reunion16 = np.array([18.9, 8.2, 8.1, 8.4, 7.6])

plt.plot(round, latency_reunion8, label='8 messages' + ' avg: ' + ("%.2f" % calc_avg(latency_reunion8)) + ' std: ' + ("%.2f" % np.std(latency_reunion8)))
plt.plot(round, latency_reunion16, label='16 messages' + ' avg: ' + ("%.2f" % calc_avg(latency_reunion16)) + ' std: ' + ("%.2f" % np.std(latency_reunion16)))
plt.xlabel('round', fontsize=16)
plt.ylabel('latency (s)', fontsize=16)
plt.title('Latency for reaching consistency after reunion of clusters')
plt.legend()
plt.show()