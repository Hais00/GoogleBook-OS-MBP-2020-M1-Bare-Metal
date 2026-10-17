/* Exercise synchronization failure with real mappings, without a GPU device. */
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <sys/mman.h>
#include "drv_priv.h"
#include "drv_array_helpers.h"

static int fail_sync, maps, unmaps;
static void *map_buffer(struct bo *bo, struct vma *vma, uint32_t flags)
{
    (void)bo; (void)flags;
    maps++;
    vma->length = 4096;
    return mmap(NULL, vma->length, PROT_READ | PROT_WRITE,
                MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
}
static int unmap_buffer(struct bo *bo, struct vma *vma)
{
    (void)bo;
    unmaps++;
    return munmap(vma->addr, vma->length);
}
static int invalidate_buffer(struct bo *bo, struct mapping *mapping)
{
    (void)bo; (void)mapping;
    return fail_sync ? -EIO : 0;
}
int main(void)
{
    const struct backend backend = {.bo_map=map_buffer, .bo_unmap=unmap_buffer,
                                    .bo_invalidate=invalidate_buffer};
    struct driver driver = {.fd=-1, .backend=&backend};
    pthread_mutex_init(&driver.mappings_lock, NULL);
    driver.mappings = drv_array_init(sizeof(struct mapping));
    assert(driver.mappings);
    struct bo bo = {.drv=&driver, .meta={.width=8, .height=8, .num_planes=1,
                    .strides={32}, .sizes={256}, .total_size=256}, .handle.u32=7};
    const struct rectangle rect = {.width=8, .height=8};
    struct mapping *mapping = NULL, *rejected = NULL;
    fail_sync=1;
    assert(drv_bo_map(&bo,&rect,BO_MAP_READ_WRITE,&rejected,0)==MAP_FAILED);
    assert(errno==EIO && rejected==NULL && drv_array_size(driver.mappings)==0);
    assert(maps==1 && unmaps==1);
    fail_sync=0;
    unsigned char *pixels=drv_bo_map(&bo,&rect,BO_MAP_READ_WRITE,&mapping,0);
    assert(pixels!=MAP_FAILED && mapping && mapping->refcount==1);
    pixels[13]=0xa5;
    fail_sync=1;
    assert(drv_bo_map(&bo,&rect,BO_MAP_READ_WRITE,&rejected,0)==MAP_FAILED);
    assert(errno==EIO && rejected==NULL && mapping->refcount==1);
    assert(drv_array_size(driver.mappings)==1 && pixels[13]==0xa5);
    assert(drv_bo_unmap(&bo,mapping)==0);
    assert(maps==2 && unmaps==2 && drv_array_size(driver.mappings)==0);
    drv_array_destroy(driver.mappings);
    pthread_mutex_destroy(&driver.mappings_lock);
    puts("MINIGBM_SYNC_FAILURE_PASS: failed new/reused mappings rejected; original mapping retained; references and mappings released");
}
