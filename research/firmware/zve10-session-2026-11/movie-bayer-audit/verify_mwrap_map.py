"""Execute native shared-map allocator/release and compare independent bit model.

RAM register/context fixtures do not represent physical buffers or ownership
fences. OS lock, logger and harness memory-helper boundaries are intercepted.
"""
import argparse,json,sys,struct
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('repo',type=Path);a=p.parse_args()
sys.path.insert(0,str(a.repo/'research/firmware/raw_frame_source/verified_yc/evidence/native-setup-20261030'))
from rtos_harness import Harness,MEM
h=Harness();h.u.mem_map(0xfc000000,0x100000)
for fn in [0x635df208,0x635df224,0x6396f8c4]:h.callbacks[fn]=lambda args:h.ret(0)
lookups={1:[3],2:[3,4],4:[2,3,4,5],6:list(range(1,7)),
         8:list(range(8)),10:list(range(10)),12:list(range(12))}
def indices(output,count):return list(range(count)) if output==0 else list(range(12-count,12))
rows=[];releases=[]
for old in [(0,0),(4,6),(6,6),(12,0),(0,12)]:
    oldmask=sum(1<<i for i in indices(0,old[0])+indices(1,old[1]))
    for output in [0,1]:
        for count in list(range(14))+[255]:
            h.run(0x637a2230,MEM)
            h.u.mem_write(MEM+4,bytes(old))
            h.put(MEM+8,oldmask)
            owner=0xabcd0a5a;mapping=0xfedcba9876543210
            h.put(0xfc0a7804,owner);h.put(0xfc0a7808,mapping&0xffffffff)
            h.put(0xfc0a780c,mapping>>32)
            result=h.run(0x637a229c,MEM,output,count)
            valid=count in lookups and old[1-output]+count<=12
            assert result==int(valid)
            newcounts=list(old);mask=oldmask
            expected_owner=owner;expected_map=mapping
            if valid:
                for i in indices(output,old[output]):mask&=~(1<<i)
                for i,v in zip(indices(output,count),lookups[count]):
                    expected_owner=(expected_owner&~(1<<i))|(output<<i)
                    expected_map=(expected_map&~(15<<(i*4)))|(v<<(i*4))
                    mask|=1<<i
                newcounts[output]=count
            assert list(h.u.mem_read(MEM+4,2))==newcounts,(old,output,count)
            assert h.word(MEM+8)==mask
            assert h.word(0xfc0a7804)==expected_owner
            actualmap=h.word(0xfc0a7808)|(h.word(0xfc0a780c)<<32)
            assert actualmap==expected_map,(old,output,count,hex(actualmap),hex(expected_map))
            rows.append(dict(old_counts=old,output=output,requested=count,returned=result,
                             new_counts=newcounts,enabled_mask=hex(mask),owner_bits=hex(expected_owner),
                             index_map=hex(expected_map)))
        # A release disables the selected range and clears its count, but leaves
        # both hardware map words and their owner bits unchanged.
        h.run(0x637a2230,MEM);h.u.mem_write(MEM+4,bytes(old));h.put(MEM+8,oldmask)
        h.put(0xfc0a7804,owner);h.put(0xfc0a7808,mapping&0xffffffff);h.put(0xfc0a780c,mapping>>32)
        h.run(0x63d24f72,MEM,output)
        expected_mask=oldmask
        for i in indices(output,old[output]):expected_mask&=~(1<<i)
        expected_counts=list(old);expected_counts[output]=0
        assert list(h.u.mem_read(MEM+4,2))==expected_counts
        assert h.word(MEM+8)==expected_mask
        assert h.word(0xfc0a7804)==owner
        assert h.word(0xfc0a7808)|(h.word(0xfc0a780c)<<32)==mapping
        releases.append(dict(old_counts=old,output=output,new_counts=expected_counts,
                             enabled_mask=hex(expected_mask),mapping_preserved=True))
print(json.dumps(dict(allocation_cases=len(rows),release_cases=len(releases),
    native_allocator='0x637a229c',native_release='0x63d24f72',
    native_index_selector='0x637a21b4',mocks=['OS locks','logger','harness memory helpers'],
    fixtures=['prior counts','prior enable mask','RAM-backed hardware owner/index maps'],
    actual_frame_memory_identified=False,dma_or_pixels_emulated=False,
    allocation_rows=rows,release_rows=releases),indent=2))
