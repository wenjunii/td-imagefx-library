uniform float uMix;
uniform vec4 uKeyColor;
uniform float uAmount;
uniform float uBalance;
uniform float uRestoreLuma;

layout(location = 0) out vec4 fragColor;

void main()
{
    vec2 uv = vUV.st;
    vec4 source = texture(sTD2DInputs[0], uv);
    vec3 keyDirection = normalize(max(uKeyColor.rgb, vec3(0.000001)));
    float sourceLuma = dot(source.rgb, vec3(0.2126, 0.7152, 0.0722));
    float keyProjection = dot(source.rgb, keyDirection);
    float excess = max(keyProjection - sourceLuma * uBalance, 0.0);
    float spillAmount = uAmount * clamp(uKeyColor.a, 0.0, 1.0);
    vec3 corrected = max(source.rgb - keyDirection * excess * spillAmount, vec3(0.0));
    float correctedLuma = dot(corrected, vec3(0.2126, 0.7152, 0.0722));
    corrected += vec3((sourceLuma - correctedLuma) * uRestoreLuma);
    vec4 despilled = vec4(corrected, source.a);
    fragColor = TDOutputSwizzle(mix(source, despilled, clamp(uMix, 0.0, 1.0)));
}
