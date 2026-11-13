#include <cstdio>
#include <cstring>

#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/micro/micro_log.h"
#include "tensorflow/lite/micro/schema/schema_generated.h"

#include "model.h"
#include "micro_model_settings.h"
#include "no_micro_features_data.h"

extern "C" void app_main(void)
{
    vTaskDelay(pdMS_TO_TICKS(4000));

    const tflite::Model *model = tflite::GetModel(g_model);
    if (model->version() != TFLITE_SCHEMA_VERSION) {
        printf("BENCH:ML|micro_speech|bad schema\n");
        return;
    }

    static tflite::MicroMutableOpResolver<4> resolver;
    resolver.AddDepthwiseConv2D();
    resolver.AddFullyConnected();
    resolver.AddSoftmax();
    resolver.AddReshape();

    static uint8_t tensor_arena[30 * 1024];
    static tflite::MicroInterpreter interpreter(model, resolver, tensor_arena,
                                                sizeof(tensor_arena));
    if (interpreter.AllocateTensors() != kTfLiteOk) {
        printf("BENCH:ML|micro_speech|alloc failed\n");
        return;
    }

    TfLiteTensor *input = interpreter.input(0);
    int n = input->bytes;
    if (n > kFeatureElementCount) {
        n = kFeatureElementCount;
    }
    memcpy(input->data.int8, g_no_micro_f9643d42_nohash_4_data, (size_t)n);

    for (int i = 0; i < 10; i++) {
        interpreter.Invoke();
    }

    const int iters = 200;
    int64_t t0 = esp_timer_get_time();
    for (int i = 0; i < iters; i++) {
        interpreter.Invoke();
    }
    int64_t us = esp_timer_get_time() - t0;

    printf("BENCH:ML|micro_speech|%.3f ms/inf|%.1f fps|%d iters|arena=%u|input=%d|model=%d\n",
           (double)us / 1000.0 / iters, (double)iters / ((double)us / 1e6), iters,
           (unsigned)sizeof(tensor_arena), n, g_model_len);

    TfLiteTensor *out = interpreter.output(0);
    printf("BENCH:ML|micro_speech_out|");
    for (int i = 0; i < kCategoryCount; i++) {
        printf("%d,", (int)out->data.int8[i]);
    }
    printf("\nBENCH:DONE\n");

    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(10000));
        printf("BENCH:ALIVE\n");
    }
}
