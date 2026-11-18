"""Inspect the audit Pico; optionally issue one reset or a brief carrier test.

Acknowledgements and GP28 transitions do not prove camera reset/execution or
the waveform at the camera connector. No payload records are sent.
"""
import argparse,json,struct,statistics
from pico_link import Link

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',required=True)
    action=p.add_mutually_exclusive_group()
    action.add_argument('--reset-only',action='store_true',help='actively pulse GP27 once, without carrier or payload')
    action.add_argument('--carrier-test',action='store_true',help='actively enable the carrier briefly and sample GP28 transitions')
    action.add_argument('--isolated-self-test',action='store_true',help='ONLY with camera physically disconnected: test GP28 using its weak internal pull-up')
    a=p.parse_args()
    link=Link(a.port)
    carrier_started=False
    bench_pull_enabled=False
    result={}
    try:
        version=link.exchange(1)
        if version!=b'zve10_uart_od 16 audit':raise RuntimeError('Expected v16 audit firmware: '+repr(version))
        result['configuration']=link.configuration()
        result['before']=link.status()
        s=result['before']
        if s['mode'] or s['blob_pending'] or s['gpio_function']!=5 or s['pull_up'] or s['pull_down'] or s['push_pull_build']:
            raise RuntimeError('Pico is not idle with released TX; stop the current sender first')
        if a.reset_only:
            link.exchange(2)
            result['reset_command_acknowledged']=True
            result['camera_reset_observed_by_tool']=False
            result['instruction']='Observe the camera: did its screen/LED change? This command sends no payload or carrier.'
        elif a.carrier_test or a.isolated_self_test:
            if a.isolated_self_test:
                # This flag asserts that the camera connector is unplugged.
                # Mark before sending so cleanup is attempted even on ACK loss.
                bench_pull_enabled=True
                link.exchange(0x07,b'\x01')
                result['isolated_pull_up_status']=link.status()
            # Mark before the command so cleanup also runs if its ACK is lost.
            carrier_started=True
            link.exchange(3,b'\x01')
            data=link.exchange(0x0a)
            if len(data)<2:raise RuntimeError('Short transition reply')
            count=struct.unpack_from('<H',data)[0]
            if count>64 or len(data)!=2+count*5:raise RuntimeError('Invalid transition reply')
            events=[struct.unpack_from('<IB',data,2+i*5) for i in range(count)]
            if any(level not in [0,1] for _,level in events):raise RuntimeError('Invalid GPIO level')
            intervals=[events[i][0]-events[i-1][0] for i in range(1,count)]
            result['gp28_transition_count']=count
            result['median_edge_interval_us']=statistics.median(intervals) if intervals else None
            result['gp28_events']=events
            result['camera_connector_waveform_verified']=False
            if a.isolated_self_test:
                pulled=result['isolated_pull_up_status']
                result['isolated_gp28_self_test_passed']=bool(pulled['pull_up'] and pulled['level'] and count>=4)
        result['after']=link.status() if not carrier_started else None
    finally:
        try:
            try:
                if carrier_started:
                    link.exchange(3,b'\x00')
            finally:
                if bench_pull_enabled:
                    link.exchange(0x07,b'\x00')
            if carrier_started or bench_pull_enabled:
                result['after']=link.status()
        finally:link.serial.close()
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
