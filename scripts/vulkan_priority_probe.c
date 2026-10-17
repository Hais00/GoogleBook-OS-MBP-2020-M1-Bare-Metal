// SPDX-License-Identifier: Apache-2.0
// Mirror RenderEngine's advertised-maximum priority selection, using real queues.
#include <vulkan/vulkan.h>
#include <stdio.h>
#include <stdint.h>

int main(void)
{
   setbuf(stdout, NULL);
   VkApplicationInfo app = { .sType = VK_STRUCTURE_TYPE_APPLICATION_INFO,
                            .apiVersion = VK_API_VERSION_1_2 };
   VkInstanceCreateInfo ici = { .sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO,
                               .pApplicationInfo = &app };
   VkInstance instance;
   if (vkCreateInstance(&ici, NULL, &instance) != VK_SUCCESS) return 2;
   uint32_t count = 1;
   VkPhysicalDevice physical;
   if (vkEnumeratePhysicalDevices(instance, &count, &physical) != VK_SUCCESS || count != 1) return 2;
   VkPhysicalDeviceDriverProperties driver = { .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_DRIVER_PROPERTIES };
   VkPhysicalDeviceProperties2 props = { .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2,
                                        .pNext = &driver };
   vkGetPhysicalDeviceProperties2(physical, &props);
   printf("PRIORITY_ACTUAL_DEVICE %s driver=%s id=%u\n", props.properties.deviceName, driver.driverName, driver.driverID);
   if (driver.driverID != VK_DRIVER_ID_MESA_HONEYKRISP) return 3;
   count = 0;
   vkGetPhysicalDeviceQueueFamilyProperties2(physical, &count, NULL);
   if (!count || count > 8) return 3;
   VkQueueFamilyProperties2 families[8] = {0};
   VkQueueFamilyGlobalPriorityPropertiesKHR priorities[8] = {0};
   for (uint32_t i = 0; i < count; i++) {
      priorities[i].sType = VK_STRUCTURE_TYPE_QUEUE_FAMILY_GLOBAL_PRIORITY_PROPERTIES_KHR;
      families[i].sType = VK_STRUCTURE_TYPE_QUEUE_FAMILY_PROPERTIES_2;
      families[i].pNext = &priorities[i];
   }
   vkGetPhysicalDeviceQueueFamilyProperties2(physical, &count, families);
   uint32_t family = 0;
   while (family < count && !(families[family].queueFamilyProperties.queueFlags & VK_QUEUE_GRAPHICS_BIT)) family++;
   if (family == count) return 3;
   VkQueueGlobalPriorityKHR maximum = VK_QUEUE_GLOBAL_PRIORITY_MEDIUM_KHR;
   for (uint32_t i = 0; i < priorities[family].priorityCount; i++) {
      printf("PRIORITY_ADVERTISED %u\n", priorities[family].priorities[i]);
      if (priorities[family].priorities[i] > maximum) maximum = priorities[family].priorities[i];
   }
   printf("RENDERENGINE_SELECTED_ADVERTISED_MAXIMUM %u\n", maximum);
   const VkQueueGlobalPriorityKHR tests[] = { VK_QUEUE_GLOBAL_PRIORITY_LOW_KHR,
      VK_QUEUE_GLOBAL_PRIORITY_MEDIUM_KHR, VK_QUEUE_GLOBAL_PRIORITY_HIGH_KHR,
      VK_QUEUE_GLOBAL_PRIORITY_REALTIME_KHR };
   const char *extensions[] = { VK_EXT_GLOBAL_PRIORITY_EXTENSION_NAME };
   unsigned failures = 0;
   for (uint32_t i = 0; i < 4; i++) {
      int advertised = 0;
      for (uint32_t j = 0; j < priorities[family].priorityCount; j++)
         advertised |= priorities[family].priorities[j] == tests[i];
      VkDeviceQueueGlobalPriorityCreateInfoKHR global = {
         .sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_GLOBAL_PRIORITY_CREATE_INFO_KHR,
         .globalPriority = tests[i] };
      float local = 0.0f;
      VkDeviceQueueCreateInfo queue = { .sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO,
         .pNext = &global, .queueFamilyIndex = family, .queueCount = 1, .pQueuePriorities = &local };
      VkDeviceCreateInfo create = { .sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO,
         .queueCreateInfoCount = 1, .pQueueCreateInfos = &queue,
         .enabledExtensionCount = 1, .ppEnabledExtensionNames = extensions };
      VkDevice device = VK_NULL_HANDLE;
      VkResult result = vkCreateDevice(physical, &create, NULL, &device);
      printf("PRIORITY_REAL_CREATE priority=%u advertised=%d result=%d selected=%d\n",
             tests[i], advertised, result, tests[i] == maximum);
      if (advertised && result != VK_SUCCESS) failures++;
      if (!advertised && tests[i] >= VK_QUEUE_GLOBAL_PRIORITY_HIGH_KHR && result != VK_ERROR_NOT_PERMITTED_KHR) failures++;
      if (tests[i] == maximum && result != VK_SUCCESS) failures++;
      if (result == VK_SUCCESS) {
         VkQueue actual;
         vkGetDeviceQueue(device, family, 0, &actual);
         if (actual == VK_NULL_HANDLE) failures++;
         if (vkDeviceWaitIdle(device) != VK_SUCCESS) failures++;
         vkDestroyDevice(device, NULL);
      }
   }
   vkDestroyInstance(instance, NULL);
   printf("PRIORITY_ADVERTISEMENT_AND_REAL_CREATION_%s failures=%u\n", failures ? "FAIL" : "PASS", failures);
   return failures ? 5 : 0;
}
